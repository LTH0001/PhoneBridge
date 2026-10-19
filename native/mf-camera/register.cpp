#include "compat.h"
#include "../../vendor/mfvirtualcamera.h"
#include <cstdio>
#include <cwchar>
int wmain(int argc,wchar_t** argv){
    HRESULT hr=CoInitializeEx(nullptr,COINIT_MULTITHREADED);if(FAILED(hr))return 1;
    hr=MFStartup(MF_VERSION);if(FAILED(hr))return 2;
    HMODULE module=LoadLibraryW(L"mfsensorgroup.dll");if(!module)return 3;
    using Create=HRESULT(WINAPI*)(MFVirtualCameraType,MFVirtualCameraLifetime,MFVirtualCameraAccess,LPCWSTR,LPCWSTR,const GUID*,ULONG,IMFVirtualCamera**);
    auto create=(Create)GetProcAddress(module,"MFCreateVirtualCamera");if(!create)return 4;
    ComPtr<IMFVirtualCamera> camera;
    hr=create(MFVirtualCameraType_SoftwareCameraSource,MFVirtualCameraLifetime_System,MFVirtualCameraAccess_AllUsers,PB_NAME,PB_CLSID,nullptr,0,&camera);
    if(SUCCEEDED(hr))hr=(argc>1 && !wcscmp(argv[1],L"remove"))?camera->Remove():camera->Start(nullptr);
    printf("PhoneBridge MF camera HRESULT=0x%08lx\n",(unsigned long)hr);
    fflush(stdout);
    if(camera)camera->Shutdown();camera.Reset();MFShutdown();CoUninitialize();return FAILED(hr)?5:0;
}
