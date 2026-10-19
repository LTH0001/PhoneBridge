"""Consent-gated public lyrics lookup and exact-track local LRC import."""
import bisect
import copy
import hashlib
import html
import json
import re
import threading
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from .config import ROOT,save_preferences,data_root

def track_key(media):
    return hashlib.sha256((str(media.get('title',''))+'\0'+str(media.get('artist',''))+'\0'+str(round(media.get('duration_seconds',0)))).encode()).hexdigest()[:24]

def parse_lrc(text):
    if not isinstance(text,str) or len(text.encode('utf-8'))>512*1024:raise ValueError('歌词过大或格式无效')
    offset=0
    match=re.search(r'\[offset:([+-]?\d+)\]',text,re.I)
    if match:offset=int(match.group(1))/1000
    lines=[]
    for raw in text.splitlines():
        stamps=list(re.finditer(r'\[(\d{1,3}):(\d{2}(?:\.\d{1,3})?)\]',raw))
        if not stamps:continue
        lyric=html.unescape(raw[stamps[-1].end():]).strip()[:600]
        if not lyric:continue
        for stamp in stamps:
            if float(stamp.group(2))>=60:continue
            second=int(stamp.group(1))*60+float(stamp.group(2))+offset
            if 0<=second<=24*3600:lines.append({'time':round(second,3),'text':lyric})
    lines.sort(key=lambda x:x['time'])
    if len(lines)>4000:raise ValueError('歌词行数过多')
    return lines

def title_for_query(title):
    # Drop translated subtitles only, not Live/Remix or meaningful English titles.
    if re.search('[A-Za-z]',title):
        title=re.sub(r'[（(][^）)]*[\u4e00-\u9fff][^）)]*[）)]','',title)
    return title.strip()

def normalized(text):return ''.join(c for c in str(text).casefold() if c.isalnum())

def artist_variants(text):
    variants=[]
    for part in reversed(re.split(r'[/,;&、]',str(text))):
        part=part.strip()
        if not part:continue
        aliases=re.findall(r'[（(]([^）)]+)[）)]',part)
        base=re.sub(r'[（(][^）)]+[）)]','',part).strip()
        for item in aliases+[base,part]:
            if item and item not in variants:variants.append(item)
    return variants

def matching_record(records,media):
    title=normalized(title_for_query(media['title']))
    artists={normalized(s) for s in artist_variants(media['artist'])}
    duration=media.get('duration_seconds',0)
    candidates=[]
    for item in records:
        if not isinstance(item,dict) or normalized(item.get('trackName',''))!=title:continue
        theirs={normalized(s) for s in artist_variants(item.get('artistName',''))}
        if not artists.intersection(theirs):continue
        try:distance=abs(float(item.get('duration',0))-duration)
        except (TypeError,ValueError):continue
        if duration<=0 or distance>4:continue
        if item.get('syncedLyrics') or item.get('instrumental') is True:candidates.append((distance,item))
    return min(candidates,key=lambda x:x[0])[1] if candidates else None

class LyricsController:
    def __init__(self,music,network_allowed=False):
        self.music=music;self.allowed=bool(network_allowed);self.lock=threading.RLock()
        self.cache={};self.loading=set();self.closed=threading.Event()

    def _base(self,media):
        return {'track_key':track_key(media),'lines':[],'state':'unavailable','source':'',
                'network_allowed':self.allowed,'note':'暂无同步歌词；可以在电脑导入本地 LRC'}

    def request(self,allow_network=False,retry=False):
        if type(allow_network) is not bool:raise ValueError('歌词联网确认必须为布尔值')
        if type(retry) is not bool:raise ValueError('重试参数必须为布尔值')
        media=self.music.status()
        if not media.get('available') or str(media.get('source_app_id','')).lower()!='qqmusic.exe':raise ValueError('没有当前 QQ 音乐会话')
        if allow_network and not self.allowed:
            save_preferences(lyrics_network_allowed=True);self.allowed=True
        key=track_key(media)
        with self.lock:
            if retry and key in self.cache and self.cache[key].get('source')!='本地 LRC':self.cache.pop(key)
            if key in self.cache:return self.status()
            file=data_root(ROOT)/'runtime/lyrics'/f'{key}.lrc'
            if file.is_file():
                try:
                    lines=parse_lrc(file.read_text('utf-8-sig'))
                    self.cache[key]={**self._base(media),'lines':lines,'state':'ready' if lines else 'unavailable','source':'本地 LRC','note':'' if lines else 'LRC 没有时间标签'}
                except (OSError,ValueError):pass
            if key not in self.cache:
                if not self.allowed:
                    return {**self._base(media),'state':'consent','note':'联网只查询当前曲目名称和歌手；需要你确认，也可导入本地 LRC'}
                if key not in self.loading:
                    self.loading.add(key)
                    threading.Thread(target=self._lookup,args=(media,key),name='pb-lyrics',daemon=True).start()
        return self.status()

    def _lookup(self,media,key):
        value=self._base(media)
        try:
            artists=artist_variants(media['artist'])
            selected=None
            # Alias queries first; a title-only fallback is still strictly matched
            # locally against artist and duration, never a closest-name guess.
            for artist in artists[:2]+['']:
                query_data={'track_name':title_for_query(media['title'])}
                if artist:query_data['artist_name']=artist
                query=urllib.parse.urlencode(query_data)
                request=urllib.request.Request('https://lrclib.net/api/search?'+query,headers={'User-Agent':'PhoneBridge/0.3 personal-use'})
                raw=self._read_online(request)
                if len(raw)>512*1024:raise ValueError('歌词服务响应过大')
                records=json.loads(raw)
                if not isinstance(records,list):raise ValueError('歌词服务格式无效')
                selected=matching_record(records[:100],media)
                if selected or self.closed.is_set():break
            if selected:
                lines=parse_lrc(selected.get('syncedLyrics') or '')
                instrumental=selected.get('instrumental') is True
                value.update(lines=lines,state='instrumental' if instrumental else 'ready' if lines else 'unavailable',source='LRCLIB',note='此曲为纯音乐，请欣赏' if instrumental else '' if lines else '此曲没有可用的时间标签')
            else:value['note']='未找到曲名、歌手和时长相符的同步歌词；可导入本地 LRC'
        except urllib.error.HTTPError as error:
            value['note']='歌词服务暂时不可用，可点击重查或导入 LRC（HTTP '+str(error.code)+'）'
        except Exception as error:value['note']='歌词查询未完成，可点击重查或导入 LRC：'+str(error)[:100]
        with self.lock:
            self.loading.discard(key)
            if not self.closed.is_set():
                if len(self.cache)>=8:self.cache.pop(next(iter(self.cache)))
                if self.cache.get(key,{}).get('source')!='本地 LRC':self.cache[key]=value

    def _read_online(self,request):
        # Retry one transient server failure only, never retry audio commands.
        for attempt in range(2):
            if self.closed.is_set():raise ValueError('歌词查询已关闭')
            try:
                with urllib.request.urlopen(request,timeout=8) as response:
                    parsed=urllib.parse.urlparse(response.url)
                    if parsed.hostname!='lrclib.net' or parsed.scheme!='https':raise ValueError('歌词服务发生非预期跳转')
                    return response.read(512*1024+1)
            except urllib.error.HTTPError as error:
                if attempt or error.code not in (502,503,504):raise
                self.closed.wait(.7)

    def import_lrc(self,path):
        # Invoked only by the local GUI file picker, not an arbitrary API path.
        media=self.music.status()
        if not media.get('available'):raise ValueError('请先播放要对应的 QQ 音乐歌曲')
        source=Path(path)
        if source.suffix.lower()!='.lrc' or source.stat().st_size>512*1024:raise ValueError('请选择小于 512 KiB 的 LRC 文件')
        text=source.read_text('utf-8-sig');lines=parse_lrc(text)
        if not lines:raise ValueError('LRC 中没有可用的时间标签')
        key=track_key(media);directory=data_root(ROOT)/'runtime/lyrics';directory.mkdir(parents=True,exist_ok=True)
        (directory/f'{key}.lrc').write_text(text,'utf-8')
        with self.lock:self.cache[key]={**self._base(media),'lines':lines,'state':'ready','source':'本地 LRC','note':''}
        return {'ok':True,'line_count':len(lines)}

    def status(self):
        media=self.music.status();key=track_key(media)
        with self.lock:
            value=copy.deepcopy(self.cache.get(key,self._base(media)))
            if key in self.loading:value.update(state='loading',note='正在查询同步歌词…')
            value['network_allowed']=self.allowed
        position=media.get('position_seconds',0)
        value['current_index']=bisect.bisect_right([x['time'] for x in value['lines']],position)-1
        value['position_seconds']=position
        value['playing']=media.get('playback_status')=='playing'
        value['playback_rate']=media.get('playback_rate',1)
        value['duration_seconds']=media.get('duration_seconds',0)
        return value

    def close(self):self.closed.set()
