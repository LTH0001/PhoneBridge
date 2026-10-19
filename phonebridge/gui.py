import io
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from .windows import camera_registered, register_camera, register_camera_system, monitors
from .cameras import preferred_camera, camera_label
from .config import save_camera_facing, save_preferences
from .layout import LAYOUTS, phone_desktop_size
from .cpu_temperature import start_sampler
from .mf_camera import register as register_mf_camera
from .mf_camera import installed as mf_camera_installed
from .desktop_style import apply_theme,ScrollPage,Foldout,device_label,BG,SIDEBAR,CARD,TEXT,MUTED,ACCENT

class ControlCenter(tk.Tk):
    def __init__(self, bridge, api, activation=None):
        super().__init__()
        self.bridge, self.api = bridge, api
        self.activation = activation
        self.title('PhoneBridge · 手机外设控制中心')
        self.geometry('1400x900')
        self.minsize(1180,760)
        self.results = queue.Queue()
        self.last_jpeg = None
        self.preview_image = None
        self.device_map = {}
        self.device_choices = {}
        self.sensor_map = {'陀螺仪 (4)': 4, '加速度计 (1)': 1, '磁力计 (2)': 2, '光线 (5)': 5, '旋转矢量 (11)': 11}
        self.busy = 0
        self._caps_revision = None
        self._build()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(200, self._tick)
        self.run(self.refresh_devices, '刷新设备')
        self.run(self.refresh_audio, '刷新音频设备')
        if bridge.connected:
            self.results.put(('ok','连接手机',bridge.status()))

    def _build(self):
        apply_theme(self)
        shell=ttk.Frame(self);shell.pack(fill='both',expand=True)
        sidebar=ttk.Frame(shell,style='Sidebar.TFrame',width=196,padding=(14,26));sidebar.pack(side='left',fill='y');sidebar.pack_propagate(False)
        ttk.Label(sidebar,text='PhoneBridge',background=SIDEBAR,font=('Segoe UI',17,'bold')).pack(anchor='w',padx=14,pady=(8,3))
        ttk.Label(sidebar,text='手机外设管理',background=SIDEBAR,foreground=MUTED,font=('Microsoft YaHei UI',9)).pack(anchor='w',padx=14,pady=(0,34))
        main=ttk.Frame(shell,padding=(28,23,23,16));main.pack(side='left',fill='both',expand=True)
        header=ttk.Frame(main);header.pack(fill='x',pady=(0,18))
        header_left=ttk.Frame(header);header_left.pack(side='left')
        self.page_title=tk.StringVar(value='设备概览')
        ttk.Label(header_left,textvariable=self.page_title,style='Title.TLabel').pack(anchor='w',pady=(4,0))
        self.connection = tk.StringVar(value='未连接')
        ttk.Label(header,textvariable=self.connection,foreground=ACCENT).pack(side='right',padx=8)
        connection=ttk.Frame(main);connection.pack(fill='x',pady=(0,15))
        self.device_choice=ttk.Combobox(connection,state='readonly',width=39)
        self.device_choice.pack(side='left',fill='x',expand=True,padx=(0,8))
        self.button(connection, '刷新', self.refresh_devices)
        self.button(connection, '连接手机', self.connect_selected)
        self.button(connection, '断开', self.bridge.disconnect)
        self.tabs=ttk.Notebook(main,style='Shell.TNotebook');self.tabs.pack(fill='both',expand=True)
        self.pages=[];self.nav_buttons=[]
        titles=['设备概览','影音外设','屏幕与触控','传感器','文件与相册','安装与帮助','诊断日志']
        for index,title in enumerate(titles):
            page=ScrollPage(self.tabs);self.tabs.add(page,text=title);self.pages.append(page)
            button=ttk.Button(sidebar,text=title,style='Nav.TButton',command=lambda i=index:self.tabs.select(i))
            button.pack(fill='x',pady=3);self.nav_buttons.append(button)
        self.tabs.bind('<<NotebookTabChanged>>',self.page_changed)
        self.bind('<MouseWheel>',self.page_wheel,add='+')
        ttk.Label(sidebar,text='Windows · Android\n本地连接，按需授权',background=SIDEBAR,foreground=MUTED,font=('Microsoft YaHei UI',8),justify='left').pack(side='bottom',anchor='w',padx=14,pady=12)
        overview,media,display,sensors,files,setup,tools=[p.body for p in self.pages]
        hero=ttk.Frame(overview,style='Card.TFrame',padding=25);hero.pack(fill='x',pady=(0,20))
        self.overview_heading=tk.StringVar(value='连接你的手机')
        self.overview_hint=tk.StringVar(value='在上方选择设备并连接，再开启需要使用的外设。')
        ttk.Label(hero,textvariable=self.overview_heading,style='Hero.TLabel').pack(anchor='w')
        ttk.Label(hero,textvariable=self.overview_hint,style='CardMuted.TLabel').pack(anchor='w',pady=(10,0))
        metrics=ttk.Frame(overview,style='Card.TFrame',padding=(6,5));metrics.pack(fill='x',pady=(0,24));self.overview_values={}
        for index,(key,title) in enumerate((('link','连接状态'),('camera','摄像头'),('microphone','麦克风'),('display','扩展屏'))):
            metrics.columnconfigure(index,weight=1,uniform='metric')
            card=ttk.Frame(metrics,style='Card.TFrame',padding=19);card.grid(row=0,column=index,sticky='nsew')
            ttk.Label(card,text=title,style='CardMuted.TLabel').pack(anchor='w')
            variable=tk.StringVar(value='待连接');self.overview_values[key]=variable
            ttk.Label(card,textvariable=variable,style='Value.TLabel').pack(anchor='w',pady=(12,0))
        quick=ttk.LabelFrame(overview,text='常用功能',padding=20);quick.pack(fill='x',pady=(0,22))
        row=ttk.Frame(quick);row.pack(fill='x')
        ttk.Button(row,text='影音外设  →',command=lambda:self.tabs.select(1),style='Primary.TButton').pack(side='left',padx=(0,10))
        ttk.Button(row,text='设置触控副屏  →',command=lambda:self.tabs.select(2)).pack(side='left',padx=(0,10))
        self.button(row,'打开手机控制面板',self.api.start_panel)
        ttk.Label(quick,text='推荐：先连接手机，再按需要启动外设。连接本身不会自动打开摄像头或麦克风。',style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=(16,0))
        guide=ttk.LabelFrame(overview,text='第一次使用？',padding=20);guide.pack(fill='x')
        ttk.Label(guide,text='01  在手机安装 PhoneBridge App\n02  打开 USB 调试，插线后允许自己的电脑\n03  在上方选择“USB 调试 · 已授权”，点击连接',justify='left').pack(anchor='w')
        ttk.Button(guide,text='查看安装与组件设置',command=lambda:self.tabs.select(5)).pack(anchor='w',pady=(15,0))
        ttk.Label(overview,text='免调试 USB 与无线配对仍为实验功能；不会自动替换手机驱动或关闭系统安全检查。',style='Muted.TLabel',wraplength=880).pack(anchor='w',pady=16)
        cam = ttk.LabelFrame(media, text='手机摄像头', padding=12); cam.pack(fill='x')
        controls = ttk.Frame(cam); controls.pack(fill='x')
        self.camera_choice = ttk.Combobox(controls, state='readonly', width=18)
        self.camera_choice.pack(side='left')
        self.camera_choice.bind('<<ComboboxSelected>>', self.remember_camera)
        self.resolution = ttk.Combobox(controls, state='readonly', values=('1280x720', '1920x1080', '640x480'), width=12)
        self.resolution.current(0); self.resolution.pack(side='left', padx=8)
        self.virtual = tk.BooleanVar(value=camera_registered() or mf_camera_installed())
        ttk.Checkbutton(controls, text='输出到 Windows 摄像头', variable=self.virtual).pack(side='left')
        self.button(controls, '启动', self.start_camera)
        self.button(controls, '停止', self.bridge.camera_stop)
        self.camera_status = tk.StringVar(value='摄像头未启动')
        ttk.Label(cam, textvariable=self.camera_status).pack(anchor='w', pady=(8, 0))
        ttk.Label(cam, text='其他软件中选择“PhoneBridge Camera”；如未出现，请重新打开该软件。').pack(anchor='w')
        ttk.Label(cam, text='默认优先前摄；手动选择会记住。选择后点击“启动”应用镜头切换。', foreground=MUTED).pack(anchor='w')
        ttk.Button(cam,text='设置系统摄像头输出  →',command=lambda:self.tabs.select(5)).pack(anchor='w',pady=(10,0))
        ttk.Label(cam,text='原生输出用于 Windows 摄像头设置/现代应用；勾选 Windows 输出后启动前摄，具体会议软件需单独验证。').pack(anchor='w')
        preview_shell=ttk.Frame(media,height=245);preview_shell.pack(fill='x',pady=16);preview_shell.pack_propagate(False)
        self.preview=ttk.Label(preview_shell,text='摄像头预览\n\n启动后显示手机画面',anchor='center',justify='center',background=CARD,foreground=MUTED)
        self.preview.pack(fill='both',expand=True)
        audio = ttk.LabelFrame(media, text='手机麦克风', padding=12); audio.pack(fill='x')
        row = ttk.Frame(audio); row.pack(fill='x')
        self.audio_choice = ttk.Combobox(row, state='readonly', width=45); self.audio_choice.pack(side='left',fill='x',expand=True)
        self.button(row, '刷新', self.refresh_audio)
        self.button(row, '启动', self.start_mic)
        self.button(row, '停止', self.bridge.mic_stop)
        self.mic_status = tk.StringVar(value='麦克风未启动')
        ttk.Label(audio, textvariable=self.mic_status).pack(anchor='w', pady=(8, 0))
        self.level = ttk.Progressbar(audio, maximum=1); self.level.pack(fill='x', pady=6)
        ttk.Label(audio, text='作为系统麦克风：输出选 VB-Audio Virtual Cable 扬声器/CABLE Input，会议软件输入选 CABLE Output。').pack(anchor='w')
        row = ttk.Frame(sensors); row.pack(fill='x')
        self.sensor_choice = ttk.Combobox(row, state='readonly', width=35, values=list(self.sensor_map)); self.sensor_choice.current(0); self.sensor_choice.pack(side='left')
        self.rate = tk.StringVar(value='100'); ttk.Spinbox(row, from_=1, to=1000, textvariable=self.rate, width=7).pack(side='left', padx=8)
        ttk.Label(row, text='Hz').pack(side='left')
        self.button(row, '订阅', self.start_sensor)
        self.button(row, '停止', self.stop_sensor)
        self.button(row, '停止所有传感器', self.stop_all_sensors)
        self.sensor_tree = ttk.Treeview(sensors, columns=('type', 'value', 'rate', 'count', 'accuracy'), show='headings', height=14)
        for name, title, width in [('type','传感器',100), ('value','实时数据',430), ('rate','实测 Hz',100), ('count','事件数',100), ('accuracy','精度',100)]:
            self.sensor_tree.heading(name, text=title); self.sensor_tree.column(name, width=width)
        self.sensor_tree.pack(fill='both', expand=True, pady=15)
        row = ttk.LabelFrame(sensors, text='手机控制', padding=12); row.pack(fill='x')
        for label, action in [('唤醒', 'wake'), ('主页', 'home'), ('返回', 'back'), ('音量 +', 'volume_up'), ('音量 −', 'volume_down')]:
            self.button(row, label, lambda a=action: self.bridge.control(a))
        self.button(row, '振动 200ms', lambda: self.bridge.control('vibrate', ms=200))
        row=ttk.Frame(sensors);row.pack(fill='x',pady=12)
        self.button(row, '手电筒开', lambda: self.bridge.control('torch', on=True))
        self.button(row, '手电筒关', lambda: self.bridge.control('torch', on=False))
        self.build_display_page(display)
        music=ttk.LabelFrame(media,text='音乐与歌词',padding=18);music.pack(fill='x',pady=(20,0))
        ttk.Label(music,text='手机控制面板提供音乐控制与歌词显示；歌词设置集中在这里。',style='Muted.TLabel').pack(anchor='w')
        lyric_row=ttk.Frame(music);lyric_row.pack(fill='x',pady=(12,8))
        self.button(lyric_row,'导入当前曲目 LRC',self.import_lyrics)
        self.lyrics_network=tk.BooleanVar(value=self.bridge.config.get('lyrics_network_allowed',False))
        ttk.Checkbutton(music,text='允许向 LRCLIB 查询当前曲名和歌手（不发送音频或账户）',variable=self.lyrics_network,command=self.remember_lyrics_network).pack(anchor='w')
        ttk.Label(files,text='通过已授权 USB 调试访问共享存储、照片和下载文件；不绕过 Android 私有数据保护。').pack(anchor='w')
        row=ttk.Frame(files); row.pack(fill='x',pady=10)
        self.file_path=tk.StringVar(value='/sdcard')
        ttk.Entry(row,textvariable=self.file_path,width=54).pack(side='left')
        self.button(row,'打开路径',self.open_file_path)
        self.button(row,'上一级',self.file_up)
        self.button(row,'下载选中文件',self.download_file)
        shortcuts=ttk.Frame(files); shortcuts.pack(fill='x')
        self.button(shortcuts,'共享文件',lambda: self.browse_files('/sdcard'))
        self.button(shortcuts,'相机相册',lambda: self.browse_files('/sdcard/DCIM'))
        self.button(shortcuts,'图片',lambda: self.browse_files('/sdcard/Pictures'))
        self.button(shortcuts,'手机下载',lambda: self.browse_files('/sdcard/Download'))
        self.button(shortcuts,'检查权限',self.check_permissions)
        self.file_entries={}
        self.file_tree=ttk.Treeview(files,columns=('name','type','size'),show='headings',height=13)
        for name,label,width in (('name','名称',540),('type','类型',100),('size','字节数',180)):
            self.file_tree.heading(name,text=label); self.file_tree.column(name,width=width)
        self.file_tree.pack(fill='both',expand=True,pady=10)
        self.file_tree.bind('<Double-1>',self.file_open_selected)
        self.permissions_text=tk.StringVar(value='其他应用私有目录、聊天数据库、系统密钥不可访问。联系人/定位等需按具体功能单独授权，不会自动授予全部权限。')
        ttk.Label(files,textvariable=self.permissions_text,wraplength=950).pack(anchor='w')
        for title,description,actions in (
            ('01 / 手机 App','其他 Android 手机也需安装 APK；USB 调试版需要手机授权自己的电脑。',(('网页 USB 安装',self.open_web_setup),('导出手机 APK',self.export_android_apk),('通过已授权 USB 安装',self.bridge.install))),
            ('02 / Windows 系统摄像头','供腾讯会议等应用选择的原生虚拟摄像头。首次注册需要管理员确认，仅支持 Windows 11。',(('注册 Windows 原生摄像头',register_mf_camera),)),
            ('03 / 独立扩展屏','首次使用需安装签名显示组件；仅点击对应按钮时才请求系统确认。',(('安装显示组件',lambda:self.driver_action('install')),('更新手机比例配置',lambda:self.driver_action('configure')))),
            ('04 / CPU 温度','使用单独的只读采集器；新电脑可能需先安装官方签名 PawnIO 前置驱动，不使用无限制版本。',(('启用 CPU 温度采集',start_sampler),)),
            ('05 / 音乐程序','自动查找本机 QQ 音乐；如果安装在非标准位置，可在这里选择 QQMusic.exe。',(('选择 QQ 音乐程序',self.choose_music_program),))):
            card=ttk.LabelFrame(setup,text=title,padding=18);card.pack(fill='x',pady=(0,18))
            ttk.Label(card,text=description,style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=(0,12))
            row=ttk.Frame(card);row.pack(fill='x')
            for text,action in actions:self.button(row,text,action)
        experiment=ttk.LabelFrame(setup,text='实验室 / 连接兼容性',padding=18);experiment.pack(fill='x',pady=(0,18))
        ttk.Label(experiment,text='稳定使用请选 USB 调试连接。免调试 AOA 尚未完成通用验收；无线连接需要可互通网络和配对。',style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=(0,12))
        ttk.Button(experiment,text='打开无线配对（实验）',command=self.wireless_pair).pack(anchor='w')
        if __import__('pathlib').Path(self.bridge.config['softcam']).is_file():
            legacy=ttk.LabelFrame(setup,text='本机旧版 DirectShow 兼容组件',padding=18);legacy.pack(fill='x',pady=(0,18))
            self.button(legacy,'注册旧版摄像头',lambda:register_camera(self.bridge.config['softcam']))
            self.button(legacy,'系统级注册（管理员）',register_camera_system)
        ttk.Label(setup,text='软件包不会自动授予手机全部权限。相机、麦克风、USB 调试和系统组件安装分别由用户确认。',style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=8)
        ttk.Label(tools, text=f'本机 API  /  http://127.0.0.1:{self.api.port}\n接口仅监听本机，调用需要访问令牌；请勿向他人分享令牌文件。\n\n完整说明及 Python SDK 示例见 README.md。',style='Muted.TLabel').pack(anchor='w')
        self.log_widget = tk.Text(tools, height=24, wrap='word', state='disabled', font=('Consolas', 10),background=CARD,foreground=TEXT,insertbackground=ACCENT,relief='flat',padx=16,pady=14)
        self.log_widget.pack(fill='both', expand=True, pady=15)
        self.footer = tk.StringVar(value='就绪')
        ttk.Label(main, textvariable=self.footer,style='Muted.TLabel').pack(anchor='w', pady=(12, 0))
        self.page_changed()

    def build_display_page(self,parent):
        second=ttk.LabelFrame(parent,text='手机副屏',padding=22);second.pack(fill='x',pady=(0,22))
        ttk.Label(second,text='将手机作为电脑的第二块屏幕，支持手机触控。',style='Muted.TLabel').pack(anchor='w')
        actions=ttk.Frame(second);actions.pack(fill='x',pady=(20,15))
        self.display_primary=self.button(actions,'启动副屏',self.display_primary_action,primary=True)
        self.display_stop_button=self.button(actions,'停止',self.bridge.display_stop)
        ttk.Separator(actions,orient='vertical').pack(side='left',fill='y',padx=14,pady=4)
        self.panel_button=self.button(actions,'打开控制面板',self.api.start_panel)
        self.display_status=tk.StringVar(value='副屏未启动')
        ttk.Label(second,textvariable=self.display_status,style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=(0,14))
        ttk.Separator(second).pack(fill='x',pady=(0,10))
        self.display_summary=tk.StringVar()
        ttk.Label(second,textvariable=self.display_summary,style='Muted.TLabel',wraplength=850).pack(anchor='w')
        self.display_settings=Foldout(second,'显示设置');self.display_settings.pack(fill='x',pady=(3,0))
        settings=self.display_settings.body;settings.columnconfigure(1,weight=1)
        self.layout_choice=ttk.Combobox(settings,state='readonly',values=list(LAYOUTS.values()),width=42)
        self.layout_choice.set(LAYOUTS.get(self.bridge.config.get('display_layout'),LAYOUTS['below-left']))
        self.desktop_size=ttk.Combobox(settings,state='readonly',width=42,
            values=('640 · 近似27寸主屏字号（推荐）','800 · 大字','1002 · 适中','1202 · 平衡','1600 · 更多内容','2404 · 原生清晰'))
        preferred=str(self.bridge.config.get('display_desktop_width',640))
        self.desktop_size.set(next((v for v in self.desktop_size['values'] if v.startswith(preferred+' ')),self.desktop_size['values'][0]))
        self.quality_choice=ttk.Combobox(settings,state='readonly',width=42,
            values=('高清锐化 · 手机原生像素 / CRF16','省资源 · 低分辨率直接传输'))
        self.quality_choice.current(0 if self.bridge.config.get('display_quality','sharp')=='sharp' else 1)
        for row,(label,widget) in enumerate((('摆放位置',self.layout_choice),('桌面大小',self.desktop_size),('传输画质',self.quality_choice))):
            ttk.Label(settings,text=label).grid(row=row,column=0,sticky='w',padx=(0,18),pady=7)
            widget.grid(row=row,column=1,sticky='ew',pady=7)
            widget.bind('<<ComboboxSelected>>',self.update_display_summary)
        self.touch=tk.BooleanVar(value=self.bridge.config.get('display_touch',True))
        ttk.Checkbutton(settings,text='允许手机触控操作电脑',variable=self.touch,command=self.update_display_summary).grid(row=3,column=1,sticky='w',pady=7)
        ttk.Label(settings,text='修改后重新启动副屏生效。大字档保留阅读尺寸；原生清晰档能显示更多内容，文字也会更小。',style='Muted.TLabel',wraplength=750).grid(row=4,column=0,columnspan=2,sticky='w',pady=(6,0))
        self.update_display_summary()
        mirror=ttk.LabelFrame(parent,text='在电脑上操作手机',padding=22);mirror.pack(fill='x',pady=(0,16))
        ttk.Label(mirror,text='在独立窗口中显示手机画面，使用电脑鼠标和键盘操作。',style='Muted.TLabel').pack(anchor='w')
        row=ttk.Frame(mirror);row.pack(fill='x',pady=(16,0))
        self.button(row,'打开手机窗口',self.bridge.screen_start)
        self.button(row,'关闭手机窗口',self.bridge.screen_stop)
        self.compatibility_settings=Foldout(parent,'兼容模式与显示诊断');self.compatibility_settings.pack(fill='x')
        legacy=self.compatibility_settings.body
        ttk.Label(legacy,text='兼容模式仅转发现有显示器画面，不会创建独立副屏。正常使用请选择上方“启动副屏”。',style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=(0,10))
        row=ttk.Frame(legacy);row.pack(fill='x')
        self.monitors=monitors()
        self.monitor_choice=ttk.Combobox(row,state='readonly',width=35,
            values=[f"{d['id']} · {d['width']}×{d['height']}"+(' 主屏' if d['primary'] else ' 副屏') for d in self.monitors])
        if self.monitors:self.monitor_choice.current(next((i for i,m in enumerate(self.monitors) if not m['primary']),0))
        self.monitor_choice.pack(side='left',fill='x',expand=True,padx=(0,12))
        self.button(row,'刷新显示器',self.refresh_monitors)
        row=ttk.Frame(legacy);row.pack(fill='x',pady=12)
        self.button(row,'兼容发送',self.start_display)
        self.button(row,'停止兼容发送',self.api.stop_display)
        self.button(row,'手动启用扩展桌面',self.enable_extended)
        ttk.Button(legacy,text='安装或修复显示组件 →',style='Disclosure.TButton',command=lambda:self.tabs.select(5)).pack(anchor='w')

    def update_display_summary(self,event=None):
        position=self.layout_choice.get().split('（')[0].strip()
        width=self.desktop_size.get().split(' · ')[0]
        quality='高清' if self.quality_choice.current()==0 else '省资源'
        self.display_summary.set(f"{position}   ·   桌面宽度 {width}   ·   {quality}   ·   "+('触控开启' if self.touch.get() else '触控关闭'))

    def display_primary_action(self):
        if self.bridge.panel_visible and self.bridge.desired_display:
            return self.api.resume_desktop
        return self.start_native_display()

    def open_web_setup(self):
        import webbrowser
        webbrowser.open(f'http://127.0.0.1:{self.api.port}/setup#token={self.api.token}')

    def choose_music_program(self):
        from pathlib import Path
        chosen=filedialog.askopenfilename(parent=self,title='选择 QQMusic.exe',filetypes=[('QQ 音乐','QQMusic.exe')])
        if not chosen:return
        path=Path(chosen)
        if not path.is_file() or path.name.casefold()!='qqmusic.exe':
            messagebox.showerror('无法设置','请选择已安装的 QQMusic.exe。',parent=self);return
        save_preferences(music_path=str(path))
        self.bridge.config['music_path']=str(path)
        with self.api.music.lock:self.api.music.path=path
        with self.api.music.window.lock:
            self.api.music.window.path=path
            self.api.music.window.updated=0
        self.footer.set('QQ 音乐程序路径已保存')

    def page_changed(self,event=None):
        index=self.tabs.index(self.tabs.select())
        self.page_title.set(self.tabs.tab(index,'text'))
        for i,button in enumerate(self.nav_buttons):button.configure(style='NavActive.TButton' if i==index else 'Nav.TButton')

    def page_wheel(self,event):
        if event.widget.winfo_class() not in ('Text','Treeview','TCombobox'):
            self.pages[self.tabs.index(self.tabs.select())].wheel(event)

    def export_android_apk(self):
        from pathlib import Path
        from .config import ROOT
        source=ROOT/'android/app/build/phonebridge.apk'
        if not source.is_file():messagebox.showerror('安装包不存在','请先构建 Android App 或重新下载完整 Windows 包。',parent=self);return
        directory=filedialog.askdirectory(title='选择保存 APK 的文件夹',parent=self)
        if not directory:return
        destination=Path(directory)/'PhoneBridge-Android.apk'
        try:
            with source.open('rb') as reader,destination.open('xb') as writer:
                import shutil
                shutil.copyfileobj(reader,writer)
            self.footer.set('APK 已导出。发送到手机后，由手机确认安装。')
        except FileExistsError:messagebox.showinfo('文件已存在','该目录已有 PhoneBridge-Android.apk，未覆盖。请另选目录。',parent=self)

    def button(self, parent, text, action, primary=False):
        b = ttk.Button(parent, text=text, command=lambda: self.run(action, text),style='Primary.TButton' if primary or text in ('连接手机','启动','启动原生副屏') else 'TButton')
        b.pack(side='left', padx=4)
        return b

    def run(self, action, label='操作'):
        if action in (self.choose_music_program,self.export_android_apk):
            return action() # Native dialogs and Tk variables stay on the UI thread.
        # Tk variables are read on the UI thread; background work receives only
        # immutable selections, never accesses Tcl from a worker.
        if action in (self.connect_selected, self.start_camera, self.start_mic, self.start_sensor, self.stop_sensor, self.start_display, self.start_native_display,self.display_primary_action, self.open_file_path, self.file_up, self.download_file,self.import_lyrics):
            try:
                action = action()
            except Exception as exc:
                self.footer.set(str(exc))
                return
        self.busy += 1
        self.footer.set(label + '…')
        def worker():
            try:
                self.results.put(('ok', label, action()))
            except Exception as exc:
                self.results.put(('error', label, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def wireless_pair(self):
        from .wireless import local_addresses
        from PIL import ImageTk
        import qrcode
        addresses=local_addresses()
        if not addresses:
            messagebox.showerror('无线配对','没有可用的局域网 IPv4 网卡');return
        dialog=tk.Toplevel(self);dialog.title('无线配对 · 无需开发者模式');dialog.geometry('650x620')
        ttk.Label(dialog,text='手机与电脑需处于可互通网络。选择电脑网卡后生成配对信息。').pack(pady=10)
        choices=ttk.Combobox(dialog,state='readonly',values=[f'{n} · {a}' for n,a in addresses],width=65);choices.current(0);choices.pack()
        note=ttk.Label(dialog,text='配对信息有效 120 秒，首次配对后失效。勿向他人分享。');note.pack(pady=8)
        qr=ttk.Label(dialog);qr.pack()
        field=tk.Text(dialog,height=4,wrap='char');field.pack(fill='x',padx=20,pady=8)
        def generate():
            try:
                result=self.api.pair_wireless(addresses[choices.current()][1])
                invitation=result['invitation'];field.delete('1.0','end');field.insert('1.0',invitation)
                code=qrcode.QRCode(box_size=4,border=4);code.add_data(invitation);code.make(fit=True);image=code.make_image().convert('RGB')
                qr.image=ImageTk.PhotoImage(image);qr.configure(image=qr.image)
                note.configure(text=f"有效 120 秒 · TLS 端口 {result['port']} · 手机输入/粘贴完整配对信息")
            except Exception as exc:messagebox.showerror('配对失败',str(exc),parent=dialog)
        ttk.Button(dialog,text='生成 / 更新配对信息（断开当前 USB）',command=generate).pack(pady=5)
        ttk.Button(dialog,text='复制配对信息',command=lambda:(dialog.clipboard_clear(),dialog.clipboard_append(field.get('1.0','end').strip()))).pack(pady=5)
        ttk.Button(dialog,text='关闭无线并撤销授权',command=lambda:(self.api.stop_wireless(),dialog.destroy())).pack(pady=5)
        # Closing the window hides the code; the user can continue an established session.

    def refresh_devices(self):
        found = self.bridge.detect_wired(include_adb=True)
        self.results.put(('devices', found))
        return found

    def import_lyrics(self):
        path=filedialog.askopenfilename(title='导入当前 QQ 音乐歌曲的同步歌词',filetypes=[('同步歌词','*.lrc')])
        if not path:return lambda:{'cancelled':True}
        return lambda:self.api.lyrics.import_lrc(path)

    def remember_lyrics_network(self):
        allowed=self.lyrics_network.get()
        save_preferences(lyrics_network_allowed=allowed)
        self.bridge.config['lyrics_network_allowed']=allowed;self.api.lyrics.allowed=allowed

    def refresh_audio(self):
        devices = self.bridge.audio.devices()
        self.results.put(('audio', devices))
        return {'output_devices': len(devices)}

    def start_camera(self):
        if not self.camera_choice.get():
            raise ValueError('请先连接手机并选择摄像头')
        cid = self.camera_choice.get().split()[0]
        w, h = map(int, self.resolution.get().split('x'))
        virtual = self.virtual.get()
        return lambda: self.bridge.camera_start(cid, w, h, 30, virtual)

    def remember_camera(self, event=None):
        cid = self.camera_choice.get().split()[0]
        camera = next((c for c in self.bridge.caps.get('camera', []) if str(c['id']) == cid), None)
        if camera is None:
            return
        try:
            facing = str(camera.get('facing', '')).upper()
            save_camera_facing(facing)
            self.bridge.config['default_camera_facing'] = facing
            self.footer.set('已记住 ' + camera_label(camera) + '；点击“启动”应用')
        except Exception as exc:
            self.footer.set('镜头选择未保存：' + str(exc))

    def refresh_cameras(self):
        cameras = self.bridge.caps.get('camera', [])
        self.camera_choice['values'] = [camera_label(c) for c in cameras if 'id' in c]
        desired = self.bridge.desired_camera
        selected = next((c for c in cameras if desired and str(c.get('id')) == desired['camera_id']), None)
        selected = selected or preferred_camera(cameras, self.bridge.config.get('default_camera_facing', 'FRONT'))
        self.camera_choice.set(camera_label(selected) if selected else '')

    def connect_selected(self):
        serial = self.device_choices.get(self.device_choice.get(),'')
        return lambda: self.bridge.connect_wired(serial)

    def start_mic(self):
        device = self.device_map.get(self.audio_choice.get(), -1)
        return lambda: self.bridge.mic_start(device)

    def start_sensor(self):
        typ = self.sensor_map[self.sensor_choice.get()]; rate = int(self.rate.get())
        return lambda: self.bridge.sensor_start(typ, rate)

    def stop_sensor(self):
        typ = self.sensor_map[self.sensor_choice.get()]
        return lambda: self.bridge.sensor_stop(typ)

    def stop_all_sensors(self):
        for sensor in list(self.bridge.desired_sensors):
            self.bridge.sensor_stop(sensor)
        return {'ok': True}

    def start_display(self):
        monitor = self.monitor_choice.current(); touch = self.touch.get()
        return lambda: self.api.start_display(monitor, touch)

    def start_native_display(self):
        monitor = self.monitor_choice.current(); touch = self.touch.get()
        layout=next(key for key,label in LAYOUTS.items() if label==self.layout_choice.get())
        width=int(self.desktop_size.get().split()[0])
        quality='sharp' if self.quality_choice.current()==0 else 'balanced'
        def start():
            result=self.bridge.display_start(monitor=monitor,touch=touch,max_width=3840,fps=30,desktop_width=width,layout=layout,
                                             dpi_scale=175 if width==2404 else 100,quality=quality)
            save_preferences(display_layout=layout,display_desktop_width=width,display_quality=quality,display_touch=touch)
            self.bridge.config.update(display_layout=layout,display_desktop_width=width,display_quality=quality,display_touch=touch)
            return result
        return start

    def browse_files(self,path):
        result=self.bridge.files.list(path)
        self.results.put(('files',result))
        return {'count':len(result['entries']),'truncated':result['truncated']}

    def open_file_path(self):
        path=self.file_path.get()
        return lambda: self.browse_files(path)

    def file_up(self):
        import posixpath
        path=self.file_path.get()
        parent=path if path in ('/sdcard','/storage/emulated/0') else posixpath.dirname(path)
        return lambda: self.browse_files(parent)

    def file_open_selected(self,event=None):
        selected=self.file_tree.selection()
        if selected:
            entry=self.file_entries[selected[0]]
            if entry['directory']: self.run(lambda: self.browse_files(entry['path']),'打开文件夹')
            else: self.footer.set('请选择“下载选中文件”保存到电脑；不会自动打开或运行手机文件')

    def download_file(self):
        selected=self.file_tree.selection()
        if not selected: raise ValueError('请先选中文件')
        entry=self.file_entries[selected[0]]
        if entry['directory']: raise ValueError('请进入文件夹后选择具体文件')
        destination=filedialog.askdirectory(title='选择保存到电脑的文件夹（不覆盖同名文件）',parent=self)
        if not destination: return lambda: {'cancelled':True}
        return lambda: self.bridge.files.download(entry['path'],destination)

    def check_permissions(self):
        result=self.bridge.files.permissions()
        self.results.put(('permissions',result))
        return {'checked':True}

    def driver_action(self, action):
        from .windows import display_driver
        return display_driver(action)

    def enable_extended(self):
        from .windows import set_virtual_display
        width,height=phone_desktop_size(self.bridge.caps.get('display',{}),self.bridge.config.get('display_desktop_width',640))
        result = set_virtual_display(True,width,height,self.bridge.config.get('display_layout','below-left'))
        self.results.put(('monitors', result))
        return {'monitors':len(result)}

    def refresh_monitors(self):
        result = monitors(); self.results.put(('monitors', result))
        return {'monitors':len(result)}

    def _tick(self):
        if self.activation and self.activation.take_activation():
            self.deiconify()
            self.lift()
            self.focus_set()
        if self.bridge.shutdown_event.is_set():
            self.destroy()
            return
        try:
            while True:
                kind, *args = self.results.get_nowait()
                if kind == 'devices':
                    previous=self.device_choice.get()
                    self.device_choices={device_label(d):d['serial'] for d in args[0]}
                    values=list(self.device_choices)
                    self.device_choice['values'] = values
                    if previous in values:self.device_choice.set(previous)
                    elif values: self.device_choice.current(0)
                    else:self.device_choice.set('')
                elif kind == 'audio':
                    self.device_map = {'只检测电平（不播放）': -1}
                    for d in args[0]:
                        self.device_map[f"{d['name']} · {d['api']}"] = d['id']
                    self.audio_choice['values'] = list(self.device_map)
                    preferred = next((n for n in self.device_map if ('CABLE Input' in n or ('VB-Audio Virtual Cable' in n and '16 Ch' not in n)) and 'WASAPI' in n), None)
                    self.audio_choice.set(preferred or '只检测电平（不播放）')
                elif kind == 'monitors':
                    self.monitors = args[0]
                    self.monitor_choice['values'] = [f"{d['id']} · {d['width']}×{d['height']}"+(' 主屏' if d['primary'] else ' 副屏') for d in self.monitors]
                    if self.monitors:
                        self.monitor_choice.current(next((i for i,m in enumerate(self.monitors) if not m['primary']),0))
                elif kind == 'files':
                    result=args[0]; self.file_path.set(result['path'])
                    self.file_tree.delete(*self.file_tree.get_children()); self.file_entries={}
                    for entry in result['entries']:
                        item=self.file_tree.insert('','end',values=(entry['name'],'文件夹' if entry['directory'] else '文件','' if entry['directory'] else entry['size']))
                        self.file_entries[item]=entry
                elif kind == 'permissions':
                    result=args[0]
                    states='、'.join(name.rsplit('.',1)[-1]+(' 已授权' if granted else ' 未授权') for name,granted in result['permissions'].items())
                    self.permissions_text.set(states+'。'+result['note'])
                else:
                    self.busy = max(0, self.busy-1)
                    if kind == 'error':
                        self.bridge.log(f'{args[0]}失败：{args[1]}')
                        self.footer.set(str(args[1]))
                    else:
                        self.footer.set(args[0] + '完成')
                        if args[0] == '连接手机':
                            sensors = self.bridge.caps.get('sensors', [])
                            self.sensor_map = {f"{s.get('name', 'Sensor')} ({s['type']})": s['type'] for s in sensors if 'type' in s}
                            self.sensor_choice['values'] = list(self.sensor_map)
                            if self.sensor_map: self.sensor_choice.current(0)
                            self.refresh_cameras()
            
        except queue.Empty:
            pass
        status = self.bridge.status()
        self.overview_heading.set('手机已连接' if status['connected'] else '连接你的手机')
        self.overview_hint.set('可以开启摄像头、麦克风或触控副屏，也可以直接打开手机控制面板。' if status['connected'] else '在上方选择设备并连接，再开启需要使用的外设。')
        revision=(status['connected'],self.bridge.serial,id(self.bridge.caps))
        if revision!=self._caps_revision:
            self._caps_revision=revision
            if status['connected']:
                self.refresh_cameras()
                sensors=self.bridge.caps.get('sensors',[])
                self.sensor_map={f"{s.get('name','Sensor')} ({s['type']})":s['type'] for s in sensors if 'type' in s}
                self.sensor_choice['values']=list(self.sensor_map)
                if self.sensor_map:self.sensor_choice.current(0)
            else:
                self.camera_choice.configure(values=[])
                self.camera_choice.set('')
        self.overview_values['link'].set(('USB 外设' if self.bridge.accessory else '无线' if self.bridge.wireless else 'USB 调试') if status['connected'] else '尚未连接')
        self.overview_values['camera'].set('运行中' if status['camera']['running'] else '已停止')
        self.overview_values['microphone'].set('运行中' if status['microphone']['running'] else '已停止')
        self.overview_values['display'].set('运行中' if status['native_display']['running'] else '控制面板' if status.get('panel_visible') else '已停止')
        self.lyrics_network.set(self.api.lyrics.allowed)
        self.connection.set(self.bridge.connection + (f' · {self.bridge.serial}' if self.bridge.serial else ''))
        cam = status['camera']; audio = status['microphone']
        self.camera_status.set(f"{cam['width']}×{cam['height']} · {cam['fps']} fps · {cam['frames']} 帧 · " + ('虚拟摄像头运行中' if cam['virtual'] else '预览' if cam['running'] else '已停止'))
        self.mic_status.set(f"{audio['packets']} 包 · 电平 {audio['level']:.3f}" + (f" · {audio['error']}" if audio['error'] else ''))
        self.level['value'] = min(audio['level']*5, 1)
        display = status['native_display']
        self.display_primary.configure(text='返回副屏' if status.get('panel_visible') and self.bridge.desired_display else '重新启动副屏' if display['running'] else '启动副屏',state='normal' if status['connected'] else 'disabled')
        self.display_stop_button.configure(state='normal' if status['connected'] and (display['running'] or status.get('panel_visible')) else 'disabled')
        self.panel_button.configure(state='normal' if status['connected'] else 'disabled')
        monitor=display.get('monitor') or {}
        self.display_status.set(('正在显示控制面板 · 点击“返回副屏”恢复电脑画面' if self.bridge.desired_display else '正在显示控制面板') if status.get('panel_visible') else
            f"桌面 {monitor.get('width',0)}×{monitor.get('height',0)} · {display['fps']} fps · {display['mbps']} Mbps" if display['running'] else
            '副屏未启动'+(f" · {display['error']}" if display['error'] else ''))
        jpeg = self.bridge.camera.jpeg
        if jpeg and jpeg is not self.last_jpeg:
            from PIL import Image, ImageTk
            im = Image.open(io.BytesIO(jpeg)); im.thumbnail((700, 225))
            self.preview_image = ImageTk.PhotoImage(im)
            self.preview.configure(image=self.preview_image, text='')
            self.last_jpeg = jpeg
        if not cam['running'] and self.last_jpeg:
            self.preview.configure(image='', text='摄像头已停止')
            self.last_jpeg = None
        self.sensor_tree.delete(*self.sensor_tree.get_children())
        for typ, value in status['sensors'].items():
            name = next((name for name, t in self.sensor_map.items() if str(t) == typ), typ)
            self.sensor_tree.insert('', 'end', values=(name, ', '.join(f'{x:.5f}' for x in value['values']),
                        value['measured_hz'] if value['active'] else '停止', value['events'], value.get('accuracy', '')))
        try:
            while True:
                log = self.bridge.events.get_nowait()
                self.log_widget.configure(state='normal')
                self.log_widget.insert('end', f"{log['time']}  {log['message']}\n")
                self.log_widget.see('end'); self.log_widget.configure(state='disabled')
        except queue.Empty:
            pass
        self.after(200, self._tick)

    def close(self):
        self.footer.set('正在关闭所有设备流…')
        def worker():
            self.api.close()
            self.bridge.close()
        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._close_poll)

    def _close_poll(self):
        if self.bridge.shutdown_event.is_set():
            self.destroy()
        else:
            self.after(100, self._close_poll)
