"""Camera selection uses device capabilities, not assumed Android camera IDs."""

def preferred_camera(cameras, facing='FRONT'):
    available = [camera for camera in cameras if 'id' in camera]
    preferred = str(facing).upper()
    return next((camera for camera in available
                 if str(camera.get('facing', '')).upper() == preferred),
                available[0] if available else None)


def camera_label(camera):
    facing = str(camera.get('facing', '')).upper()
    return f"{camera['id']} " + {'FRONT': '前置', 'BACK': '后置', 'EXTERNAL': '外接'}.get(facing, '其他')
