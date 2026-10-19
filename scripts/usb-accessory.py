"""Explicit AOA readiness / transition helper. Does not install drivers or use ADB."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from phonebridge.accessory import backend,devices,probe,switch
import usb.core,usb.util
parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['list','probe','switch'])
parser.add_argument('--vid',type=lambda x:int(x,0))
parser.add_argument('--pid',type=lambda x:int(x,0))
args=parser.parse_args()
if args.action=='list':
    print(json.dumps({'accessories':[{'vid':hex(d.idVendor),'pid':hex(d.idProduct)} for d in devices()]}));sys.exit()
if args.vid is None or args.pid is None:parser.error('probe/switch requires exact --vid and --pid; no scanning unrelated devices')
found=list(usb.core.find(find_all=True,backend=backend(),idVendor=args.vid,idProduct=args.pid))
if len(found)!=1:raise SystemExit('Expected exactly one matching device; no device was changed.')
device=found[0]
try:
    version=probe(device)
    print(json.dumps({'protocol':version,'supported':True,'changed':False}))
    if args.action=='switch':
        switch(device);print('Accessory transition requested. USB re-enumerates; MTP/ADB may disconnect. No driver changed.')
except usb.core.USBError as error:
    raise SystemExit('USB access failed: '+str(error)+'. Close competing USB/debug clients; do not replace drivers blindly.')
finally:usb.util.dispose_resources(device)
