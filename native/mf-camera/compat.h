#pragma once
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mferror.h>
#include <wrl/client.h>
// Public ABI definitions from Microsoft win32metadata's current SDK headers.
// MinGW's installed SDK predates these Windows 11 interfaces.
const GUID PB_IID_Stream2={0xc5bc37d6,0x75c7,0x46a1,{0xa1,0x32,0x81,0xb5,0xf7,0x23,0xc2,0x0f}};
const GUID PB_IID_Allocator={0xda62b958,0x3a38,0x4a97,{0xbd,0x27,0x14,0x9c,0x64,0x0c,0x07,0x71}};
enum PBStreamState { PB_STOPPED=0, PB_PAUSED=1, PB_RUNNING=2 };
struct PBStream2:IMFMediaStream {
    virtual HRESULT STDMETHODCALLTYPE SetStreamState(PBStreamState)=0;
    virtual HRESULT STDMETHODCALLTYPE GetStreamState(PBStreamState*)=0;
};
struct PBAllocatorControl:IUnknown {
    virtual HRESULT STDMETHODCALLTYPE SetDefaultAllocator(DWORD,IUnknown*)=0;
    virtual HRESULT STDMETHODCALLTYPE GetAllocatorUsage(DWORD,DWORD*,int*)=0;
};
const GUID PB_CATEGORY={0x2939e7b8,0xa62e,0x4579,{0xb6,0x74,0xd4,0x07,0x3d,0xfa,0xbb,0xba}};
const GUID PB_STREAM_ID={0x11bd5120,0xd124,0x446b,{0x88,0xe6,0x17,0x06,0x02,0x57,0xff,0xf9}};
const GUID PB_SHARED={0x1cb378e9,0xb279,0x41d4,{0xaf,0x97,0x34,0xa2,0x43,0xe6,0x83,0x20}};
const GUID PB_COLOR={0x17145fd1,0x1b2b,0x423c,{0x80,0x01,0x2b,0x68,0x33,0xed,0x35,0x88}};
const GUID PB_CAPTURE={0xfb6c4281,0x0353,0x11d1,{0x90,0x5f,0x00,0x00,0xc0,0xcc,0x16,0xba}};
const GUID CLSID_PhoneBridgeMF={0x984ae39c,0x1b89,0x4f77,{0xaa,0x3f,0x80,0x49,0x64,0x22,0xd6,0x61}};
const wchar_t PB_CLSID[]=L"{984AE39C-1B89-4F77-AA3F-80496422D661}";
const wchar_t PB_NAME[]=L"PhoneBridge Camera";
constexpr DWORD PB_WIDTH=1280, PB_HEIGHT=720, PB_BYTES=PB_WIDTH*PB_HEIGHT*4, PB_HEADER=64;
using Microsoft::WRL::ComPtr;
#define TRY(x) do { HRESULT pbhr=(x); if(FAILED(pbhr)) return pbhr; } while(0)
#define PB_EVENTS \
 HRESULT STDMETHODCALLTYPE GetEvent(DWORD f,IMFMediaEvent** e) override { auto q=EventQueue(); return q ? q->GetEvent(f,e) : MF_E_SHUTDOWN; } \
 HRESULT STDMETHODCALLTYPE BeginGetEvent(IMFAsyncCallback* cb,IUnknown* s) override { auto q=EventQueue(); return q ? q->BeginGetEvent(cb,s) : MF_E_SHUTDOWN; } \
 HRESULT STDMETHODCALLTYPE EndGetEvent(IMFAsyncResult* r,IMFMediaEvent** e) override { auto q=EventQueue(); return q ? q->EndGetEvent(r,e) : MF_E_SHUTDOWN; } \
 HRESULT STDMETHODCALLTYPE QueueEvent(MediaEventType t,REFGUID g,HRESULT h,const PROPVARIANT* p) override { auto q=EventQueue(); return q ? q->QueueEventParamVar(t,g,h,p) : MF_E_SHUTDOWN; }
