"""Physical placement and phone-aspect desktop geometry."""
LAYOUTS = {'below-left': '主屏下方靠左（上边贴主屏下边）',
           'left-bottom': '主屏左侧、底边对齐', 'left-top': '主屏左侧、上边对齐',
           'right': '主屏右侧、上边对齐'}

def phone_desktop_size(display, width=800):
    width = int(width)
    if not 640 <= width <= 3840:
        raise ValueError('副屏桌面宽度应为 640–3840')
    long_side = max(int(display.get('width', 2404)), int(display.get('height', 1080)))
    short_side = min(int(display.get('width', 2404)), int(display.get('height', 1080)))
    if short_side <= 0:
        raise ValueError('手机屏幕尺寸无效')
    return width // 2 * 2, max(2, round(width * short_side / long_side / 2) * 2)

def desktop_position(main, width, height, layout='below-left'):
    x, y = main['left'], main['top']
    if layout == 'below-left': return x, y + main['height']
    if layout == 'left-bottom': return x-width, y+main['height']-height
    if layout == 'left-top': return x-width, y
    if layout == 'right': return x+main['width'], y
    raise ValueError('未知的副屏位置')
