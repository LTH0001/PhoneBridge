#include "compat.h"
#include <mfreadwrite.h>
#include <cstdio>
#include <cwchar>
int wmain(int argc,wchar_t**) {
    CoInitializeEx(nullptr,COINIT_MULTITHREADED);MFStartup(MF_VERSION);
    ComPtr<IMFAttributes> attrs;MFCreateAttributes(&attrs,2);
    attrs->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    IMFActivate** list=nullptr;UINT32 count=0;HRESULT hr=MFEnumDeviceSources(attrs.Get(),&list,&count);
    if(FAILED(hr)){printf("ENUM error 0x%08lx\n",(ULONG)hr);return 2;}
    ComPtr<IMFMediaSource> source;
    for(UINT32 i=0;i<count;i++) {
        WCHAR* name=nullptr;UINT32 length=0;list[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME,&name,&length);
        if(name && wcsstr(name,L"PhoneBridge Camera")) {
            printf("FOUND PhoneBridge MF camera\n");fflush(stdout);
            hr=list[i]->ActivateObject(IID_IMFMediaSource,(void**)&source);
        }
        CoTaskMemFree(name);list[i]->Release();
    }
    CoTaskMemFree(list);
    if(!source){printf("ACTIVATE/NOT FOUND 0x%08lx\n",(ULONG)hr);return 3;}
    if(argc>1){source->Shutdown();puts("ENUM PASS");return 0;}
    ComPtr<IMFAttributes> options;MFCreateAttributes(&options,2);options->SetUINT32(MF_SOURCE_READER_ENABLE_VIDEO_PROCESSING,1);
    ComPtr<IMFSourceReader> reader;hr=MFCreateSourceReaderFromMediaSource(source.Get(),options.Get(),&reader);
    if(FAILED(hr)){printf("READER 0x%08lx\n",(ULONG)hr);return 4;}
    ComPtr<IMFMediaType> type;MFCreateMediaType(&type);type->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video);type->SetGUID(MF_MT_SUBTYPE,MFVideoFormat_RGB32);
    hr=reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,nullptr,type.Get());
    if(FAILED(hr)){printf("TYPE 0x%08lx\n",(ULONG)hr);return 5;}
    int frames=0,real=0;ULONGLONG began=GetTickCount64();
    while(frames<60) {
        DWORD flags=0;LONGLONG time;ComPtr<IMFSample> sample;
        hr=reader->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,nullptr,&flags,&time,&sample);
        if(FAILED(hr)){printf("READ 0x%08lx\n",(ULONG)hr);return 6;}
        if(!sample)continue;
        ComPtr<IMFMediaBuffer> buffer;sample->ConvertToContiguousBuffer(&buffer);BYTE* bytes;DWORD length;buffer->Lock(&bytes,nullptr,&length);
        unsigned long sum=0;for(DWORD i=0;i<length;i+=64)sum+=bytes[i];if(sum>length/64)real++;
        buffer->Unlock();frames++;
    }
    printf("FRAMES=%d REAL=%d ELAPSED_MS=%llu\n",frames,real,GetTickCount64()-began);
    reader.Reset();source->Shutdown();MFShutdown();CoUninitialize();return real>30?0:7;
}
