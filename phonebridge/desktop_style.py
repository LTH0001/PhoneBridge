"""Code-native desktop theme and scrollable pages; no web/CDN dependency."""
import re
import tkinter as tk
from tkinter import ttk

BG='#f7f8fa'; SIDEBAR='#eef0f4'; CARD='#ffffff'; EDGE='#dce1e8'
TEXT='#252c38'; MUTED='#647082'; ACCENT='#376bc1'; BLUE='#376bc1'

def device_label(device):
    serial=device['serial']
    if device.get('transport')=='accessory':
        return '实验 USB 外设 · '+device['state']+' · '+device.get('detail','')
    model=re.search(r'\bmodel:(\S+)',device.get('detail',''))
    name=model.group(1).replace('_',' ') if model else 'Android 手机'
    state={'device':'已授权','unauthorized':'请在手机允许调试','offline':'设备离线'}.get(device['state'],device['state'])
    return f'{name} · USB 调试 · {state} · {serial}'

def apply_theme(root):
    root.configure(background=BG)
    root.option_add('*TCombobox*Listbox.background',CARD)
    root.option_add('*TCombobox*Listbox.foreground',TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground',EDGE)
    root.option_add('*TCombobox*Listbox.selectForeground',ACCENT)
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('.',background=BG,foreground=TEXT,font=('Microsoft YaHei UI',10))
    style.configure('TFrame',background=BG)
    style.configure('Sidebar.TFrame',background=SIDEBAR)
    style.configure('Card.TFrame',background=CARD)
    style.configure('TLabel',background=BG,foreground=TEXT)
    style.configure('Muted.TLabel',foreground=MUTED)
    style.configure('Card.TLabel',background=CARD)
    style.configure('CardMuted.TLabel',background=CARD,foreground=MUTED)
    style.configure('Title.TLabel',font=('Microsoft YaHei UI',21,'bold'))
    style.configure('Hero.TLabel',background=CARD,font=('Microsoft YaHei UI',16,'bold'))
    style.configure('Value.TLabel',background=CARD,font=('Microsoft YaHei UI',15,'bold'))
    style.configure('Eyebrow.TLabel',foreground=ACCENT,font=('Segoe UI',9,'bold'))
    style.configure('TButton',background=CARD,foreground=TEXT,bordercolor=EDGE,
                    lightcolor=CARD,darkcolor=CARD,borderwidth=1,padding=(13,9))
    style.map('TButton',background=[('pressed','#e5e9f0'),('active','#f0f3f8')],foreground=[('disabled','#929baa')])
    style.configure('Primary.TButton',background=ACCENT,foreground='#ffffff',bordercolor=ACCENT,
                    font=('Microsoft YaHei UI',10,'bold'))
    style.map('Primary.TButton',background=[('pressed','#2854a0'),('active','#4579ce')],foreground=[('disabled','#e1e7f0')])
    style.configure('Nav.TButton',background=SIDEBAR,foreground=MUTED,borderwidth=0,
                    bordercolor=SIDEBAR,lightcolor=SIDEBAR,darkcolor=SIDEBAR,anchor='w',padding=(18,14))
    style.map('Nav.TButton',background=[('active','#e3e7ee')],foreground=[('active',TEXT)])
    style.configure('NavActive.TButton',background='#dfe8f8',foreground=ACCENT,borderwidth=0,
                    anchor='w',padding=(18,14),font=('Microsoft YaHei UI',10,'bold'))
    style.map('NavActive.TButton',background=[('active','#d5e1f5')])
    style.configure('Disclosure.TButton',background=BG,foreground=MUTED,borderwidth=0,
                    bordercolor=BG,lightcolor=BG,darkcolor=BG,anchor='w',padding=(0,10))
    style.map('Disclosure.TButton',background=[('active',BG)],foreground=[('active',ACCENT)])
    style.configure('TLabelframe',background=BG,bordercolor=EDGE,lightcolor=EDGE,darkcolor=EDGE,borderwidth=1)
    style.configure('TLabelframe.Label',foreground=TEXT,background=BG,font=('Microsoft YaHei UI',11,'bold'))
    style.configure('TEntry',fieldbackground=CARD,foreground=TEXT,insertcolor=ACCENT,bordercolor=EDGE,padding=7)
    style.configure('TCombobox',fieldbackground=CARD,background=CARD,foreground=TEXT,arrowcolor=MUTED,bordercolor=EDGE,padding=7)
    style.map('TCombobox',fieldbackground=[('readonly',CARD)],foreground=[('readonly',TEXT)],selectbackground=[('readonly',CARD)],selectforeground=[('readonly',TEXT)])
    style.configure('TSpinbox',fieldbackground=CARD,background=CARD,foreground=TEXT,arrowcolor=MUTED,padding=7)
    style.configure('TCheckbutton',background=BG,foreground=TEXT,indicatorbackground=CARD,indicatorforeground=ACCENT,padding=5)
    style.map('TCheckbutton',background=[('active',BG)],indicatorbackground=[('selected',ACCENT)])
    style.configure('Horizontal.TProgressbar',background=ACCENT,troughcolor=CARD,bordercolor=EDGE,lightcolor=ACCENT,darkcolor=ACCENT)
    style.configure('Treeview',background=CARD,fieldbackground=CARD,foreground=TEXT,rowheight=33,bordercolor=EDGE)
    style.configure('Treeview.Heading',background='#eef1f5',foreground=MUTED,padding=10,bordercolor=EDGE)
    style.map('Treeview',background=[('selected','#e1ebfb')],foreground=[('selected',TEXT)])
    style.configure('Vertical.TScrollbar',background=EDGE,troughcolor=BG,arrowcolor=MUTED,bordercolor=BG)
    style.configure('Shell.TNotebook',background=BG,bordercolor=BG,lightcolor=BG,darkcolor=BG,borderwidth=0,tabmargins=0)
    style.layout('Shell.TNotebook.Tab',[])
    return style

class Foldout(ttk.Frame):
    """Secondary controls stay discoverable without competing with actions."""
    def __init__(self,parent,title):
        super().__init__(parent)
        self.title=title;self.expanded=False
        self.toggle_button=ttk.Button(self,text=title+'  ▸',style='Disclosure.TButton',command=self.toggle)
        self.toggle_button.pack(fill='x')
        self.body=ttk.Frame(self,padding=(0,4,0,12))

    def toggle(self):
        self.expanded=not self.expanded
        if self.expanded:self.body.pack(fill='x')
        else:self.body.pack_forget()
        self.toggle_button.configure(text=self.title+('  ▾' if self.expanded else '  ▸'))

class ScrollPage(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.canvas=tk.Canvas(self,background=BG,highlightthickness=0,borderwidth=0)
        bar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        bar.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=bar.set)
        self.body=ttk.Frame(self.canvas,padding=(3,8,16,16))
        self.item=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self.body.bind('<Configure>',self.sync)
        self.canvas.bind('<Configure>',self.sync)

    def sync(self,event=None):
        self.canvas.itemconfigure(self.item,width=max(1,self.canvas.winfo_width()))
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def wheel(self,event):
        if self.canvas.bbox('all') and self.body.winfo_reqheight()>self.canvas.winfo_height():
            self.canvas.yview_scroll(-int(event.delta/120),'units')

def connection_diagram(parent):
    canvas=tk.Canvas(parent,width=260,height=130,background=CARD,highlightthickness=0)
    canvas.create_rectangle(12,35,108,98,outline=BLUE,width=2)
    canvas.create_line(42,106,78,106,fill=BLUE,width=3)
    canvas.create_line(60,98,60,106,fill=BLUE,width=2)
    canvas.create_text(60,66,text='PC',fill=TEXT,font=('Segoe UI',16,'bold'))
    canvas.create_line(121,67,181,67,fill=ACCENT,width=3,dash=(4,4))
    canvas.create_oval(144,60,158,74,fill=ACCENT,outline=CARD)
    canvas.create_rectangle(194,16,246,116,outline=ACCENT,width=2)
    canvas.create_line(212,25,229,25,fill=ACCENT,width=2)
    for y,width in ((48,26),(62,19),(76,26)):
        canvas.create_line(207,y,207+width,y,fill=EDGE,width=5)
    canvas.create_oval(216,103,224,111,outline=MUTED)
    return canvas
