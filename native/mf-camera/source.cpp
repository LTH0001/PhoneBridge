// PhoneBridge's own CPU-buffer Media Foundation camera source.
// Architecture informed by Microsoft's VirtualCamera sample and smourier/VCamSample.
#include "compat.h"
#include <atomic>
#include <mutex>
#include <vector>
#include <string>
#include <cstring>
#include <algorithm>
#include <shlobj.h>
#include <propvarutil.h>

static HMODULE module;
static std::atomic<long> objects(0);
struct Lifetime { Lifetime(){++objects;} ~Lifetime(){--objects;} };
static std::wstring FramePath() {
    wchar_t folder[MAX_PATH];
    if(FAILED(SHGetFolderPathW(nullptr,CSIDL_COMMON_APPDATA,nullptr,SHGFP_TYPE_CURRENT,folder))) return L"";
    return std::wstring(folder)+L"\\PhoneBridge\\CameraFrames\\frame.bin";
}

class Frames {
    HANDLE file=INVALID_HANDLE_VALUE, mapping=nullptr;
    const BYTE* view=nullptr;
public:
    ~Frames(){Close();}
    void Close(){ if(view) UnmapViewOfFile(view); if(mapping) CloseHandle(mapping); if(file!=INVALID_HANDLE_VALUE) CloseHandle(file); view=nullptr;mapping=nullptr;file=INVALID_HANDLE_VALUE; }
    bool Copy(BYTE* dest) {
        if(!view) {
            file=CreateFileW(FramePath().c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
            if(file==INVALID_HANDLE_VALUE) return false;
            LARGE_INTEGER size;
            if(!GetFileSizeEx(file,&size) || size.QuadPart!=PB_HEADER+PB_BYTES) {Close();return false;}
            mapping=CreateFileMappingW(file,nullptr,PAGE_READONLY,0,0,nullptr);
            if(mapping) view=(const BYTE*)MapViewOfFile(mapping,FILE_MAP_READ,0,0,PB_HEADER+PB_BYTES);
            if(!view){Close();return false;}
        }
        auto header=(const volatile DWORD*)view;
        if(header[0]!=0x46434250 || header[1]!=PB_WIDTH || header[2]!=PB_HEIGHT) return false;
        for(int i=0;i<3;i++) {
            DWORD sequence=header[3]; if(sequence&1) continue;
            MemoryBarrier();
            ULONGLONG tick=*(const volatile ULONGLONG*)(view+16);
            if(!tick || GetTickCount64()-tick>2500) return false;
            std::memcpy(dest,view+PB_HEADER,PB_BYTES); MemoryBarrier();
            if(sequence==header[3]) return true;
        }
        return false;
    }
};

static HRESULT MakeType(REFGUID subtype,IMFMediaType** out) {
    ComPtr<IMFMediaType> type; TRY(MFCreateMediaType(&type));
    TRY(type->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video)); TRY(type->SetGUID(MF_MT_SUBTYPE,subtype));
    TRY(MFSetAttributeSize(type.Get(),MF_MT_FRAME_SIZE,PB_WIDTH,PB_HEIGHT));
    TRY(MFSetAttributeRatio(type.Get(),MF_MT_FRAME_RATE,30,1)); TRY(MFSetAttributeRatio(type.Get(),MF_MT_PIXEL_ASPECT_RATIO,1,1));
    TRY(type->SetUINT32(MF_MT_INTERLACE_MODE,MFVideoInterlace_Progressive));
    TRY(type->SetUINT32(MF_MT_ALL_SAMPLES_INDEPENDENT,TRUE)); TRY(type->SetUINT32(MF_MT_FIXED_SIZE_SAMPLES,TRUE));
    bool nv=subtype==MFVideoFormat_NV12;
    TRY(type->SetUINT32(MF_MT_DEFAULT_STRIDE,nv?PB_WIDTH:PB_WIDTH*4));
    TRY(type->SetUINT32(MF_MT_SAMPLE_SIZE,nv?PB_WIDTH*PB_HEIGHT*3/2:PB_BYTES));
    TRY(type->SetUINT32(MF_MT_AVG_BITRATE,(nv?PB_WIDTH*PB_HEIGHT*12:PB_BYTES*8)*30));
    *out=type.Detach(); return S_OK;
}

class Stream final: public PBStream2, public Lifetime {
    std::atomic<ULONG> refs{1}; std::recursive_mutex lock;
    ComPtr<IMFMediaEventQueue> queue; ComPtr<IMFStreamDescriptor> descriptor;
    ComPtr<IMFAttributes> attributes;
    IMFMediaSource* source=nullptr; PBStreamState state=PB_STOPPED;
    GUID format=MFVideoFormat_NV12; Frames frames;
    std::vector<BYTE> rgb; ULONGLONG nextTick=0;
public:
    Stream(IMFMediaSource* src):source(src),rgb(PB_BYTES){}
    HRESULT Init() {
        TRY(MFCreateEventQueue(&queue)); TRY(MFCreateAttributes(&attributes,5));
        TRY(attributes->SetGUID(PB_CATEGORY,PB_CAPTURE)); TRY(attributes->SetUINT32(PB_STREAM_ID,0));
        TRY(attributes->SetUINT32(PB_SHARED,1)); TRY(attributes->SetUINT32(PB_COLOR,1));
        ComPtr<IMFMediaType> nv,rg; TRY(MakeType(MFVideoFormat_NV12,&nv)); TRY(MakeType(MFVideoFormat_RGB32,&rg));
        IMFMediaType* types[]={nv.Get(),rg.Get()}; TRY(MFCreateStreamDescriptor(0,2,types,&descriptor));
        ComPtr<IMFMediaTypeHandler> handler; TRY(descriptor->GetMediaTypeHandler(&handler));
        return handler->SetCurrentMediaType(nv.Get());
    }
    ComPtr<IMFMediaEventQueue> EventQueue(){std::lock_guard<std::recursive_mutex> g(lock);return queue;}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** out) override {
        if(!out)return E_POINTER; *out=nullptr;
        if(iid==IID_IUnknown || iid==IID_IMFMediaEventGenerator || iid==IID_IMFMediaStream || iid==PB_IID_Stream2) *out=(PBStream2*)this;
        else if(iid==IID_IMFAttributes) return attributes.CopyTo((IMFAttributes**)out);
        else return E_NOINTERFACE; AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override{return ++refs;}
    ULONG STDMETHODCALLTYPE Release() override{ULONG r=--refs;if(!r)delete this;return r;}
    PB_EVENTS
    HRESULT STDMETHODCALLTYPE GetMediaSource(IMFMediaSource** out) override {std::lock_guard<std::recursive_mutex> g(lock);if(!out)return E_POINTER;*out=source;if(!source)return MF_E_SHUTDOWN;source->AddRef();return S_OK;}
    HRESULT STDMETHODCALLTYPE GetStreamDescriptor(IMFStreamDescriptor** out) override {std::lock_guard<std::recursive_mutex> g(lock);return descriptor?descriptor.CopyTo(out):MF_E_SHUTDOWN;}
    HRESULT Attributes(IMFAttributes** out){return attributes.CopyTo(out);}
    HRESULT Start(IMFMediaType* type) {
        std::lock_guard<std::recursive_mutex> g(lock); if(!queue)return MF_E_SHUTDOWN;
        if(type) {
            GUID selected; UINT32 w,h; TRY(type->GetGUID(MF_MT_SUBTYPE,&selected)); TRY(MFGetAttributeSize(type,MF_MT_FRAME_SIZE,&w,&h));
            if(w!=PB_WIDTH || h!=PB_HEIGHT || (selected!=MFVideoFormat_NV12 && selected!=MFVideoFormat_RGB32))return MF_E_INVALIDMEDIATYPE;
            format=selected; ComPtr<IMFMediaTypeHandler> handler; TRY(descriptor->GetMediaTypeHandler(&handler)); TRY(handler->SetCurrentMediaType(type));
        }
        state=PB_RUNNING;nextTick=0;return queue->QueueEventParamVar(MEStreamStarted,GUID_NULL,S_OK,nullptr);
    }
    HRESULT Stop(){std::lock_guard<std::recursive_mutex> g(lock);if(!queue)return MF_E_SHUTDOWN;state=PB_STOPPED;return queue->QueueEventParamVar(MEStreamStopped,GUID_NULL,S_OK,nullptr);}
    void Shutdown(){std::lock_guard<std::recursive_mutex> g(lock);state=PB_STOPPED;source=nullptr;if(queue)queue->Shutdown();queue.Reset();descriptor.Reset();frames.Close();}
    HRESULT STDMETHODCALLTYPE SetStreamState(PBStreamState value) override {
        if(value==PB_RUNNING)return Start(nullptr);if(value==PB_STOPPED)return Stop();
        std::lock_guard<std::recursive_mutex> g(lock);state=value;return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetStreamState(PBStreamState* out) override {if(!out)return E_POINTER;std::lock_guard<std::recursive_mutex> g(lock);*out=state;return S_OK;}
    HRESULT STDMETHODCALLTYPE RequestSample(IUnknown* token) override {
        std::lock_guard<std::recursive_mutex> g(lock); if(!queue)return MF_E_SHUTDOWN;if(state!=PB_RUNNING)return MF_E_INVALIDREQUEST;
        ULONGLONG tick=GetTickCount64();if(nextTick>tick && nextTick-tick<40)Sleep((DWORD)(nextTick-tick));nextTick=GetTickCount64()+33;
        if(!frames.Copy(rgb.data()))std::fill(rgb.begin(),rgb.end(),0); // no retained personal image after sender stops
        bool nv=format==MFVideoFormat_NV12;DWORD size=nv?PB_WIDTH*PB_HEIGHT*3/2:PB_BYTES;
        ComPtr<IMFMediaBuffer> buffer; ComPtr<IMFSample> sample;TRY(MFCreateMemoryBuffer(size,&buffer));TRY(MFCreateSample(&sample));
        BYTE* dest;TRY(buffer->Lock(&dest,nullptr,nullptr));
        if(!nv)std::memcpy(dest,rgb.data(),PB_BYTES);
        else {
            BYTE* uv=dest+PB_WIDTH*PB_HEIGHT;
            auto clamp=[](int x){return (BYTE)std::max(0,std::min(255,x));};
            for(DWORD y=0;y<PB_HEIGHT;y++)for(DWORD x=0;x<PB_WIDTH;x++) {
                BYTE* p=rgb.data()+(y*PB_WIDTH+x)*4;int b=p[0],g=p[1],r=p[2];
                dest[y*PB_WIDTH+x]=clamp(((66*r+129*g+25*b+128)>>8)+16);
                if(!(x&1) && !(y&1)) {
                    int rb=0,gb=0,bb=0;
                    for(int dy=0;dy<2;dy++)for(int dx=0;dx<2;dx++){BYTE* q=p+(dy*PB_WIDTH+dx)*4;bb+=q[0];gb+=q[1];rb+=q[2];}
                    r=rb/4;g=gb/4;b=bb/4;DWORD i=(y/2)*PB_WIDTH+x;
                    uv[i]=clamp(((-38*r-74*g+112*b+128)>>8)+128);uv[i+1]=clamp(((112*r-94*g-18*b+128)>>8)+128);
                }
            }
        }
        buffer->Unlock();TRY(buffer->SetCurrentLength(size));TRY(sample->AddBuffer(buffer.Get()));
        TRY(sample->SetSampleTime(MFGetSystemTime()));TRY(sample->SetSampleDuration(333333));
        if(token)TRY(sample->SetUnknown(MFSampleExtension_Token,token));
        return queue->QueueEventParamUnk(MEMediaSample,GUID_NULL,S_OK,sample.Get());
    }
};

class Source final:public IMFMediaSourceEx,public PBAllocatorControl,public IMFGetService,public Lifetime {
    std::atomic<ULONG> refs{1};std::recursive_mutex lock;
    ComPtr<IMFAttributes> attributes;ComPtr<IMFMediaEventQueue> queue;
    ComPtr<IMFPresentationDescriptor> descriptor;ComPtr<Stream> stream;bool announced=false;
public:
    ~Source(){Shutdown();}
    HRESULT Init(IMFAttributes* attrs) {
        TRY(MFCreateAttributes(&attributes,8));if(attrs)TRY(attrs->CopyAllItems(attributes.Get()));
        TRY(attributes->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID));
        TRY(MFCreateEventQueue(&queue));stream.Attach(new Stream(this));TRY(stream->Init());
        ComPtr<IMFStreamDescriptor> desc;TRY(stream->GetStreamDescriptor(&desc));IMFStreamDescriptor* list[]={desc.Get()};
        TRY(MFCreatePresentationDescriptor(1,list,&descriptor));return descriptor->SelectStream(0);
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** out) override {
        if(!out)return E_POINTER;*out=nullptr;
        if(iid==IID_IUnknown || iid==IID_IMFMediaEventGenerator || iid==IID_IMFMediaSource || iid==IID_IMFMediaSourceEx)*out=(IMFMediaSourceEx*)this;
        else if(iid==PB_IID_Allocator)*out=(PBAllocatorControl*)this;
        else if(iid==IID_IMFGetService)*out=(IMFGetService*)this;
        else return E_NOINTERFACE;AddRef();return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override{return ++refs;}
    ULONG STDMETHODCALLTYPE Release() override{ULONG r=--refs;if(!r)delete this;return r;}
    ComPtr<IMFMediaEventQueue> EventQueue(){std::lock_guard<std::recursive_mutex> g(lock);return queue;}
    PB_EVENTS
    HRESULT STDMETHODCALLTYPE CreatePresentationDescriptor(IMFPresentationDescriptor** out) override {std::lock_guard<std::recursive_mutex> g(lock);return descriptor?descriptor->Clone(out):MF_E_SHUTDOWN;}
    HRESULT STDMETHODCALLTYPE GetCharacteristics(DWORD* out) override {if(!out)return E_POINTER;*out=MFMEDIASOURCE_IS_LIVE;return S_OK;}
    HRESULT STDMETHODCALLTYPE Start(IMFPresentationDescriptor* pd,const GUID* tf,const PROPVARIANT* position) override {
        if(!pd || !position)return E_POINTER;if(tf && *tf!=GUID_NULL)return MF_E_UNSUPPORTED_TIME_FORMAT;
        std::lock_guard<std::recursive_mutex> g(lock);if(!queue)return MF_E_SHUTDOWN;
        DWORD count;TRY(pd->GetStreamDescriptorCount(&count));if(count!=1)return E_INVALIDARG;
        BOOL selected;ComPtr<IMFStreamDescriptor> desc;TRY(pd->GetStreamDescriptorByIndex(0,&selected,&desc));if(!selected)return E_INVALIDARG;
        ComPtr<IMFMediaTypeHandler> handler;ComPtr<IMFMediaType> type;TRY(desc->GetMediaTypeHandler(&handler));TRY(handler->GetCurrentMediaType(&type));
        TRY(queue->QueueEventParamUnk(announced?MEUpdatedStream:MENewStream,GUID_NULL,S_OK,(IMFMediaStream*)stream.Get()));announced=true;
        TRY(stream->Start(type.Get()));PROPVARIANT time;PropVariantInit(&time);time.vt=VT_I8;time.hVal.QuadPart=MFGetSystemTime();
        return queue->QueueEventParamVar(MESourceStarted,GUID_NULL,S_OK,&time);
    }
    HRESULT STDMETHODCALLTYPE Stop() override {std::lock_guard<std::recursive_mutex> g(lock);if(!queue)return MF_E_SHUTDOWN;TRY(stream->Stop());return queue->QueueEventParamVar(MESourceStopped,GUID_NULL,S_OK,nullptr);}
    HRESULT STDMETHODCALLTYPE Pause() override{return MF_E_INVALID_STATE_TRANSITION;}
    HRESULT STDMETHODCALLTYPE Shutdown() override {std::lock_guard<std::recursive_mutex> g(lock);if(!queue)return MF_E_SHUTDOWN;queue->Shutdown();queue.Reset();if(stream)stream->Shutdown();stream.Reset();descriptor.Reset();return S_OK;}
    HRESULT STDMETHODCALLTYPE GetSourceAttributes(IMFAttributes** out) override{return attributes.CopyTo(out);}
    HRESULT STDMETHODCALLTYPE GetStreamAttributes(DWORD id,IMFAttributes** out) override {std::lock_guard<std::recursive_mutex> g(lock);if(id || !stream)return E_INVALIDARG;return stream->Attributes(out);}
    HRESULT STDMETHODCALLTYPE SetD3DManager(IUnknown*) override{return S_OK;} // CPU samples; no device-dependent D3D resources
    HRESULT STDMETHODCALLTYPE SetDefaultAllocator(DWORD id,IUnknown*) override{return id?E_INVALIDARG:S_OK;}
    HRESULT STDMETHODCALLTYPE GetAllocatorUsage(DWORD id,DWORD* input,int* usage) override {if(id)return E_INVALIDARG;if(!input||!usage)return E_POINTER;*input=0;*usage=1;return S_OK;} // custom allocator
    HRESULT STDMETHODCALLTYPE GetService(REFGUID,REFIID,void** out) override {if(out)*out=nullptr;return MF_E_UNSUPPORTED_SERVICE;}
};

// IMFActivate's attribute methods are delegated to the MF implementation.
#define ATTR(name,args,call) HRESULT STDMETHODCALLTYPE name args override { return attrs->name call; }
class Activator final:public IMFActivate,public Lifetime {
    std::atomic<ULONG> refs{1};std::mutex lock;ComPtr<IMFAttributes> attrs;ComPtr<Source> source;
public:
    HRESULT Init(){return MFCreateAttributes(&attrs,8);}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** out) override {if(!out)return E_POINTER;*out=nullptr;if(iid!=IID_IUnknown&&iid!=IID_IMFAttributes&&iid!=IID_IMFActivate)return E_NOINTERFACE;*out=(IMFActivate*)this;AddRef();return S_OK;}
    ULONG STDMETHODCALLTYPE AddRef() override{return ++refs;}
    ULONG STDMETHODCALLTYPE Release() override{ULONG r=--refs;if(!r)delete this;return r;}
    ATTR(GetItem,(REFGUID k,PROPVARIANT* v),(k,v)) ATTR(GetItemType,(REFGUID k,MF_ATTRIBUTE_TYPE* v),(k,v))
    ATTR(CompareItem,(REFGUID k,REFPROPVARIANT v,BOOL* b),(k,v,b)) ATTR(Compare,(IMFAttributes* a,MF_ATTRIBUTES_MATCH_TYPE m,BOOL* b),(a,m,b))
    ATTR(GetUINT32,(REFGUID k,UINT32* v),(k,v)) ATTR(GetUINT64,(REFGUID k,UINT64* v),(k,v)) ATTR(GetDouble,(REFGUID k,double* v),(k,v)) ATTR(GetGUID,(REFGUID k,GUID* v),(k,v))
    ATTR(GetStringLength,(REFGUID k,UINT32* n),(k,n)) ATTR(GetString,(REFGUID k,LPWSTR s,UINT32 n,UINT32* r),(k,s,n,r)) ATTR(GetAllocatedString,(REFGUID k,LPWSTR* s,UINT32* n),(k,s,n))
    ATTR(GetBlobSize,(REFGUID k,UINT32* n),(k,n)) ATTR(GetBlob,(REFGUID k,UINT8* b,UINT32 n,UINT32* r),(k,b,n,r)) ATTR(GetAllocatedBlob,(REFGUID k,UINT8** b,UINT32* n),(k,b,n))
    ATTR(GetUnknown,(REFGUID k,REFIID i,LPVOID* p),(k,i,p)) ATTR(SetItem,(REFGUID k,REFPROPVARIANT v),(k,v)) ATTR(DeleteItem,(REFGUID k),(k)) ATTR(DeleteAllItems,(),())
    ATTR(SetUINT32,(REFGUID k,UINT32 v),(k,v)) ATTR(SetUINT64,(REFGUID k,UINT64 v),(k,v)) ATTR(SetDouble,(REFGUID k,double v),(k,v)) ATTR(SetGUID,(REFGUID k,REFGUID v),(k,v))
    ATTR(SetString,(REFGUID k,LPCWSTR v),(k,v)) ATTR(SetBlob,(REFGUID k,const UINT8* b,UINT32 n),(k,b,n)) ATTR(SetUnknown,(REFGUID k,IUnknown* p),(k,p))
    ATTR(LockStore,(),()) ATTR(UnlockStore,(),()) ATTR(GetCount,(UINT32* n),(n)) ATTR(GetItemByIndex,(UINT32 i,GUID* k,PROPVARIANT* v),(i,k,v)) ATTR(CopyAllItems,(IMFAttributes* d),(d))
    HRESULT STDMETHODCALLTYPE ActivateObject(REFIID iid,void** out) override {std::lock_guard<std::mutex> g(lock);if(!source){source.Attach(new Source());TRY(source->Init(attrs.Get()));}return source->QueryInterface(iid,out);}
    HRESULT STDMETHODCALLTYPE ShutdownObject() override {std::lock_guard<std::mutex> g(lock);if(source)source->Shutdown();source.Reset();return S_OK;}
    HRESULT STDMETHODCALLTYPE DetachObject() override {std::lock_guard<std::mutex> g(lock);source.Reset();return S_OK;}
};

class Factory final:public IClassFactory,public Lifetime {
    std::atomic<ULONG> refs{1};
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** out) override {if(!out)return E_POINTER;*out=nullptr;if(iid!=IID_IUnknown&&iid!=IID_IClassFactory)return E_NOINTERFACE;*out=(IClassFactory*)this;AddRef();return S_OK;}
    ULONG STDMETHODCALLTYPE AddRef() override{return ++refs;}
    ULONG STDMETHODCALLTYPE Release() override{ULONG r=--refs;if(!r)delete this;return r;}
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer,REFIID iid,void** out) override {if(outer)return CLASS_E_NOAGGREGATION;ComPtr<Activator> a;a.Attach(new Activator());TRY(a->Init());return a->QueryInterface(iid,out);}
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) override {if(lock)++objects;else --objects;return S_OK;}
};
extern "C" __declspec(dllexport) HRESULT __stdcall DllGetClassObject(REFCLSID clsid,REFIID iid,void** out){if(clsid!=CLSID_PhoneBridgeMF)return CLASS_E_CLASSNOTAVAILABLE;ComPtr<Factory> f;f.Attach(new Factory());return f->QueryInterface(iid,out);}
extern "C" __declspec(dllexport) HRESULT __stdcall DllCanUnloadNow(){return objects?S_FALSE:S_OK;}
extern "C" __declspec(dllexport) HRESULT __stdcall DllRegisterServer(){
    wchar_t path[MAX_PATH];if(!GetModuleFileNameW(module,path,MAX_PATH))return HRESULT_FROM_WIN32(GetLastError());
    std::wstring key=std::wstring(L"SOFTWARE\\Classes\\CLSID\\")+PB_CLSID+L"\\InprocServer32";HKEY handle;
    LONG r=RegCreateKeyExW(HKEY_LOCAL_MACHINE,key.c_str(),0,nullptr,0,KEY_WRITE,nullptr,&handle,nullptr);if(r)return HRESULT_FROM_WIN32(r);
    r=RegSetValueExW(handle,nullptr,0,REG_SZ,(const BYTE*)path,(DWORD)(wcslen(path)+1)*2);
    if(!r)r=RegSetValueExW(handle,L"ThreadingModel",0,REG_SZ,(const BYTE*)L"Both",10);RegCloseKey(handle);return HRESULT_FROM_WIN32(r);
}
extern "C" __declspec(dllexport) HRESULT __stdcall DllUnregisterServer(){std::wstring key=std::wstring(L"SOFTWARE\\Classes\\CLSID\\")+PB_CLSID;return HRESULT_FROM_WIN32(RegDeleteTreeW(HKEY_LOCAL_MACHINE,key.c_str()));}
BOOL WINAPI DllMain(HINSTANCE h,DWORD reason,LPVOID){if(reason==DLL_PROCESS_ATTACH){module=h;DisableThreadLibraryCalls(h);}return TRUE;}
