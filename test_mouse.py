import ctypes
import struct
import time
import keyboard
import threading
from ctypes import wintypes


# ============================================================
# CONFIGURATION
# ============================================================

# Virtual Mouse HID Interface GUID
DEVICE_INTERFACE_GUID = "{1abc05c0-c378-41b9-9cef-df1aba82b015}"

# IOCTL from the existing driver code
IOCTL_SEND_MOUSE = 0x2A2010


# ============================================================
# MOUSE BUTTONS
# ============================================================

BTN_LEFT = 0x01
BTN_RIGHT = 0x02
BTN_MIDDLE = 0x04

# Works on your system as XBUTTON1
BTN_SIDE1 = 0x08

# Works on your system as XBUTTON2
BTN_SIDE2 = 0x10


# ============================================================
# F9 SETTINGS
# ============================================================

# Maximum time the left mouse button stays pressed
F9_DOWN_TIME = 0.200

# Pause between two F9 clicks
F9_PAUSE_TIME = 0.020


# ============================================================
# BUTTON 1 / XBUTTON1 SETTINGS (For ~60 FPS / 16ms cycle)
# ============================================================

# XBUTTON1 stays pressed for this long (2 ms)
SIDE1_DOWN_TIME = 0.002

# Pause between two XBUTTON1 clicks (14 ms)
SIDE1_PAUSE_TIME = 0.014


# ============================================================
# BUTTON 2 / XBUTTON2 SETTINGS (For ~60 FPS / 16ms cycle)
# ============================================================

# XBUTTON2 stays pressed for this long (2 ms)
SIDE2_DOWN_TIME = 0.002

# Pause between two XBUTTON2 clicks (14 ms)
SIDE2_PAUSE_TIME = 0.014


# ============================================================
# BUTTON 3 / MIDDLE SETTINGS (For ~60 FPS / 16ms cycle)
# ============================================================

# MIDDLE stays pressed for this long (2 ms)
SIDE3_DOWN_TIME = 0.002

# Pause between two MIDDLE clicks (14 ms)
SIDE3_PAUSE_TIME = 0.014


# ============================================================
# WINDOWS CONSTANTS
# ============================================================

DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010

GENERIC_READ_WRITE = 0xC0000000
FILE_SHARE_BOTH = 0x00000003
OPEN_EXISTING = 3

STATUS_SUCCESS = 0


# ============================================================
# SHARED BUTTON STATE
# ============================================================

button_lock = threading.Lock()

current_buttons = 0


# ============================================================
# PROGRAM / THREAD CONTROL
# ============================================================

# Set when the program should be terminated.
stop_event = threading.Event()

# Keys are physically pressed.
f9_active = threading.Event()
side1_active = threading.Event()
side2_active = threading.Event()
side3_active = threading.Event()


# Prevents Windows key-repeat from
# generating multiple start events.
f9_key_down = False
side1_key_down = False
side2_key_down = False
side3_key_down = False

key_state_lock = threading.Lock()


# ============================================================
# WINDOWS STRUCTURES
# ============================================================

class GUID(ctypes.Structure):

    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, text):

        raw = bytes.fromhex(
            text.strip("{}").replace("-", "")
        )

        return cls(
            int.from_bytes(raw[0:4], "big"),
            int.from_bytes(raw[4:6], "big"),
            int.from_bytes(raw[6:8], "big"),
            (ctypes.c_ubyte * 8)(*raw[8:16]),
        )


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class IO_STATUS_BLOCK(ctypes.Structure):

    _fields_ = [
        ("Status", ctypes.c_ssize_t),
        ("Information", ctypes.c_size_t),
    ]


# ============================================================
# WINDOWS DLLs
# ============================================================

setupapi = ctypes.WinDLL(
    "setupapi",
    use_last_error=True
)

kernel32 = ctypes.WinDLL(
    "kernel32",
    use_last_error=True
)

ntdll = ctypes.WinDLL(
    "ntdll"
)


# ============================================================
# SETUPAPI
# ============================================================

setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE

setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUID),
    wintypes.LPCWSTR,
    wintypes.HANDLE,
    wintypes.DWORD,
]


setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL

setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(GUID),
    wintypes.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
]


setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL

setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]


setupapi.SetupDiDestroyDeviceInfoList.argtypes = [
    wintypes.HANDLE
]


# ============================================================
# KERNEL32
# ============================================================

kernel32.CreateFileW.restype = wintypes.HANDLE

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]


kernel32.CloseHandle.argtypes = [
    wintypes.HANDLE
]


# ============================================================
# NTDLL
# ============================================================

ntdll.NtDeviceIoControlFile.restype = ctypes.c_long

ntdll.NtDeviceIoControlFile.argtypes = [
    wintypes.HANDLE,
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(IO_STATUS_BLOCK),
    wintypes.ULONG,
    ctypes.c_void_p,
    wintypes.ULONG,
    ctypes.c_void_p,
    wintypes.ULONG,
]


# ============================================================
# HID MOUSE REPORT
# ============================================================

def make_report(
    buttons=0,
    dx=0,
    dy=0,
    wheel=0
):
    """
    7-Byte HID Mouse Report.

    Byte 0:
        Buttons

    Byte 1:
        Reserved / Padding

    Byte 2-3:
        X

    Byte 4-5:
        Y

    Byte 6:
        Wheel
    """

    return struct.pack(
        "<BBhhB",
        buttons & 0xFF,
        0,
        max(-32768, min(32767, int(dx))),
        max(-32768, min(32767, int(dy))),
        wheel & 0xFF,
    )


# ============================================================
# FIND DEVICE INTERFACE
# ============================================================

def find_mouse_devices():

    guid = GUID.from_string(
        DEVICE_INTERFACE_GUID
    )

    info_set = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )

    invalid_handle = wintypes.HANDLE(-1).value

    if info_set == invalid_handle:

        error = ctypes.get_last_error()

        raise RuntimeError(
            f"SetupDiGetClassDevsW failed. "
            f"Windows error: {error}"
        )

    paths = []

    try:

        index = 0

        while True:

            interface_data = SP_DEVICE_INTERFACE_DATA()

            interface_data.cbSize = (
                ctypes.sizeof(interface_data)
            )

            success = (
                setupapi.SetupDiEnumDeviceInterfaces(
                    info_set,
                    None,
                    ctypes.byref(guid),
                    index,
                    ctypes.byref(interface_data),
                )
            )

            if not success:
                break

            required_size = wintypes.DWORD()

            setupapi.SetupDiGetDeviceInterfaceDetailW(
                info_set,
                ctypes.byref(interface_data),
                None,
                0,
                ctypes.byref(required_size),
                None,
            )

            if required_size.value == 0:

                index += 1
                continue

            detail_header_size = (
                8
                if ctypes.sizeof(ctypes.c_void_p) == 8
                else 6
            )

            buffer = ctypes.create_string_buffer(
                required_size.value
            )

            ctypes.cast(
                buffer,
                ctypes.POINTER(wintypes.DWORD)
            )[0] = detail_header_size

            success = (
                setupapi.SetupDiGetDeviceInterfaceDetailW(
                    info_set,
                    ctypes.byref(interface_data),
                    buffer,
                    required_size.value,
                    None,
                    None,
                )
            )

            if success:

                path_offset = ctypes.sizeof(
                    wintypes.DWORD
                )

                path = ctypes.wstring_at(
                    ctypes.addressof(buffer)
                    + path_offset
                )

                paths.append(path)

            index += 1

    finally:

        setupapi.SetupDiDestroyDeviceInfoList(
            info_set
        )

    return paths


# ============================================================
# OPEN DEVICE
# ============================================================

def open_device(path):

    invalid_handle = wintypes.HANDLE(-1).value

    handle = kernel32.CreateFileW(
        path,
        GENERIC_READ_WRITE,
        FILE_SHARE_BOTH,
        None,
        OPEN_EXISTING,
        0,
        None,
    )

    if handle == invalid_handle:

        error = ctypes.get_last_error()

        print(
            f"CreateFileW failed. "
            f"Windows error: {error}"
        )

        return None

    return handle


# ============================================================
# SEND IOCTL
# ============================================================

def send_report(handle, report):

    iosb = IO_STATUS_BLOCK()

    report_buffer = ctypes.create_string_buffer(
        report
    )

    status = ntdll.NtDeviceIoControlFile(
        handle,
        None,
        None,
        None,
        ctypes.byref(iosb),
        IOCTL_SEND_MOUSE,
        report_buffer,
        len(report),
        None,
        0,
    )

    status &= 0xFFFFFFFF

    return status


# ============================================================
# BUTTON STATE
# ============================================================

def set_button(
    handle,
    button,
    pressed
):
    """
    Sets or releases exactly one button.

    Important:
    If stop_event is set, no further
    normal mouse reports will be sent.
    """

    global current_buttons

    with button_lock:

        # Do not send normal reports after ESC/F12.
        if stop_event.is_set():
            return False

        if pressed:

            current_buttons |= button

        else:

            current_buttons &= ~button

        report = make_report(
            buttons=current_buttons
        )

        status = send_report(
            handle,
            report
        )

        return status == STATUS_SUCCESS


# ============================================================
# RELEASE ALL BUTTONS
# ============================================================

def release_all_buttons(handle):

    global current_buttons

    if handle is None:
        return

    with button_lock:

        current_buttons = 0

        status = send_report(
            handle,
            make_report(
                buttons=0,
                dx=0,
                dy=0,
                wheel=0
            )
        )

    if status != STATUS_SUCCESS:

        print(
            f"WARNING: Could not release all "
            f"virtual mouse buttons. "
            f"Status: 0x{status:08X}"
        )

    else:

        print(
            "All virtual mouse buttons released."
        )


# ============================================================
# F9 WORKER
# ============================================================

def f9_worker(handle):

    print(
        "F9 Worker started."
    )

    while not stop_event.is_set():

        # Wait until F9 is pressed.
        if not f9_active.wait(0.05):
            continue

        if stop_event.is_set():
            break

        # ----------------------------------------------------
        # LEFT DOWN
        # ----------------------------------------------------

        # print("F9 -> LEFT DOWN")  # <-- Commented out for performance

        if not set_button(
            handle,
            BTN_LEFT,
            True
        ):
            break

        # ----------------------------------------------------
        # Hold LEFT pressed
        # ----------------------------------------------------

        start = time.perf_counter()

        while (
            f9_active.is_set()
            and not stop_event.is_set()
            and (
                time.perf_counter() - start
                < F9_DOWN_TIME
            )
        ):

            time.sleep(0.005)

        # ----------------------------------------------------
        # LEFT UP
        # ----------------------------------------------------

        if not stop_event.is_set():

            # print("F9 -> LEFT UP")  # <-- Commented out for performance

            set_button(
                handle,
                BTN_LEFT,
                False
            )

        # ----------------------------------------------------
        # Pause
        # ----------------------------------------------------

        if stop_event.wait(
            F9_PAUSE_TIME
        ):
            break


# ============================================================
# BUTTON 1 / XBUTTON1 WORKER
# ============================================================

def side1_worker(handle):

    print(
        "SIDE1 Worker started."
    )

    while not stop_event.is_set():

        # Wait until Button 1 is pressed.
        if not side1_active.wait(0.05):
            continue

        if stop_event.is_set():
            break

        # ----------------------------------------------------
        # XBUTTON1 DOWN
        # ----------------------------------------------------

        # print("1 -> XBUTTON1 DOWN")  # <-- Commented out for performance

        if not set_button(
            handle,
            BTN_SIDE1,
            True
        ):
            break

        # ----------------------------------------------------
        # Hold XBUTTON1 pressed
        # ----------------------------------------------------

        start = time.perf_counter()

        while (
            side1_active.is_set()
            and not stop_event.is_set()
            and (
                time.perf_counter() - start
                < SIDE1_DOWN_TIME
            )
        ):
            
            time.sleep(0)

        # ----------------------------------------------------
        # XBUTTON1 UP
        # ----------------------------------------------------

        if not stop_event.is_set():

            # print("1 -> XBUTTON1 UP")  # <-- Commented out for performance

            set_button(
                handle,
                BTN_SIDE1,
                False
            )

        # ----------------------------------------------------
        # Pause
        # ----------------------------------------------------

        if stop_event.wait(
            SIDE1_PAUSE_TIME
        ):
            break


# ============================================================
# BUTTON 2 / XBUTTON2 WORKER
# ============================================================

def side2_worker(handle):

    print(
        "SIDE2 Worker started."
    )

    while not stop_event.is_set():

        # Wait until Button 2 is pressed.
        if not side2_active.wait(0.05):
            continue

        if stop_event.is_set():
            break

        # ----------------------------------------------------
        # XBUTTON2 DOWN
        # ----------------------------------------------------

        # print("2 -> XBUTTON2 DOWN")  # <-- Commented out for performance

        if not set_button(
            handle,
            BTN_SIDE2,
            True
        ):
            break

        # ----------------------------------------------------
        # Hold XBUTTON2 pressed
        # ----------------------------------------------------

        start = time.perf_counter()

        while (
            side2_active.is_set()
            and not stop_event.is_set()
            and (
                time.perf_counter() - start
                < SIDE2_DOWN_TIME
            )
        ):
            
            time.sleep(0)

        # ----------------------------------------------------
        # XBUTTON2 UP
        # ----------------------------------------------------

        if not stop_event.is_set():

            # print("2 -> XBUTTON2 UP")  # <-- Commented out for performance

            set_button(
                handle,
                BTN_SIDE2,
                False
            )

        # ----------------------------------------------------
        # Pause
        # ----------------------------------------------------

        if stop_event.wait(
            SIDE2_PAUSE_TIME
        ):
            break


# ============================================================
# BUTTON 3 / MIDDLE WORKER
# ============================================================

def side3_worker(handle):

    print(
        "SIDE3 Worker started."
    )

    while not stop_event.is_set():

        # Wait until Button 3 is pressed.
        if not side3_active.wait(0.05):
            continue

        if stop_event.is_set():
            break

        # ----------------------------------------------------
        # MIDDLE DOWN
        # ----------------------------------------------------

        # print("3 -> MIDDLE DOWN")  # <-- Commented out for performance

        if not set_button(
            handle,
            BTN_MIDDLE,
            True
        ):
            break

        # ----------------------------------------------------
        # Hold MIDDLE pressed
        # ----------------------------------------------------

        start = time.perf_counter()

        while (
            side3_active.is_set()
            and not stop_event.is_set()
            and (
                time.perf_counter() - start
                < SIDE3_DOWN_TIME
            )
        ):
            
            time.sleep(0)

        # ----------------------------------------------------
        # MIDDLE UP
        # ----------------------------------------------------

        if not stop_event.is_set():

            # print("3 -> MIDDLE UP")  # <-- Commented out for performance

            set_button(
                handle,
                BTN_MIDDLE,
                False
            )

        # ----------------------------------------------------
        # Pause
        # ----------------------------------------------------

        if stop_event.wait(
            SIDE3_PAUSE_TIME
        ):
            break


# ============================================================
# F9 KEY EVENT
# ============================================================

def on_f9_press(event):

    global f9_key_down

    with key_state_lock:

        if f9_key_down:
            return

        f9_key_down = True
        f9_active.set()


def on_f9_release(event):

    global f9_key_down

    with key_state_lock:

        f9_key_down = False
        f9_active.clear()


# ============================================================
# BUTTON 1 KEY EVENT
# ============================================================

def on_side1_press(event):

    global side1_key_down

    with key_state_lock:

        if side1_key_down:
            return

        side1_key_down = True
        side1_active.set()


def on_side1_release(event):

    global side1_key_down

    with key_state_lock:

        side1_key_down = False
        side1_active.clear()


# ============================================================
# BUTTON 2 KEY EVENT
# ============================================================

def on_side2_press(event):

    global side2_key_down

    with key_state_lock:

        if side2_key_down:
            return

        side2_key_down = True
        side2_active.set()


def on_side2_release(event):

    global side2_key_down

    with key_state_lock:

        side2_key_down = False
        side2_active.clear()


# ============================================================
# BUTTON 3 KEY EVENT
# ============================================================

def on_side3_press(event):

    global side3_key_down

    with key_state_lock:

        if side3_key_down:
            return

        side3_key_down = True
        side3_active.set()


def on_side3_release(event):

    global side3_key_down

    with key_state_lock:

        side3_key_down = False
        side3_active.clear()


# ============================================================
# ESC - TRUE EMERGENCY STOP
# ============================================================

def emergency_stop(handle):

    print()
    print(
        "!!! ESC - EMERGENCY STOP !!!"
    )

    stop_event.set()

    f9_active.clear()
    side1_active.clear()
    side2_active.clear()
    side3_active.clear()

    release_all_buttons(handle)

    print(
        "Emergency stop executed. Program is terminating."
    )


# ============================================================
# F12 - NORMAL EXIT
# ============================================================

def normal_exit(handle):

    print()
    print(
        "F12 -> Program is terminating."
    )

    stop_event.set()

    f9_active.clear()
    side1_active.clear()
    side2_active.clear()
    side3_active.clear()


# ============================================================
# MAIN PROGRAM
# ============================================================

def main():

    global current_buttons

    print()
    print("=" * 65)
    print("Virtual Mouse HID")
    print("F9 + Button 1 + Button 2 + Button 3 Auto-Clicker")
    print("=" * 65)
    print()

    print(
        "Searching for virtual mouse interface..."
    )

    # ========================================================
    # SEARCH DEVICE
    # ========================================================

    try:

        devices = find_mouse_devices()

    except Exception as e:

        print()
        print(f"ERROR searching for device:\n{e}")
        return

    if not devices:

        print()
        print("NO virtual mouse interface found.")
        return

    print(f"Found devices: {len(devices)}\n")

    handle = None
    f9_thread = None
    side1_thread = None
    side2_thread = None
    side3_thread = None

    try:

        # ====================================================
        # OPEN DEVICE
        # ====================================================

        for path in devices:

            print("Device:")
            print(path)
            print("\nOpening device...")

            handle = open_device(path)

            if handle is not None:
                print("OK - Device opened.")
                break

        if handle is None:

            print("\nERROR: No device could be opened.")
            return

        # ====================================================
        # RESET EVENTS
        # ====================================================

        stop_event.clear()
        f9_active.clear()
        side1_active.clear()
        side2_active.clear()
        side3_active.clear()

        # ====================================================
        # START WORKERS
        # ====================================================

        f9_thread = threading.Thread(
            target=f9_worker,
            args=(handle,),
            daemon=False,
            name="F9-AutoClicker"
        )

        side1_thread = threading.Thread(
            target=side1_worker,
            args=(handle,),
            daemon=False,
            name="XBUTTON1-AutoClicker"
        )
        
        side2_thread = threading.Thread(
            target=side2_worker,
            args=(handle,),
            daemon=False,
            name="XBUTTON2-AutoClicker"
        )

        side3_thread = threading.Thread(
            target=side3_worker,
            args=(handle,),
            daemon=False,
            name="MIDDLE-AutoClicker"
        )

        f9_thread.start()
        side1_thread.start()
        side2_thread.start()
        side3_thread.start()

        # ====================================================
        # KEYBOARD HOOKS
        # ====================================================

        # button c used for testing
        keyboard.on_press_key("c", on_f9_press)
        keyboard.on_release_key("c", on_f9_release)

        keyboard.on_press_key("1", on_side1_press)
        keyboard.on_release_key("1", on_side1_release)

        keyboard.on_press_key("2", on_side2_press)
        keyboard.on_release_key("2", on_side2_release)

        keyboard.on_press_key("3", on_side3_press)
        keyboard.on_release_key("3", on_side3_release)

        keyboard.on_press_key(
            "esc",
            lambda event: emergency_stop(handle)
        )

        # ====================================================
        # STATUS
        # ====================================================

        print()
        print("=" * 65)
        print("MOUSE IS READY")
        print("=" * 65)
        print()
        print("F9:")
        print("  Hold -> left mouse button")
        print("  200 ms DOWN, 20 ms Pause")
        print()
        print("Button 1:")
        print("  Hold -> XBUTTON1 (BTN_SIDE1)")
        print("  2 ms DOWN, 14 ms Pause")
        print()
        print("Button 2:")
        print("  Hold -> XBUTTON2 (BTN_SIDE2)")
        print("  2 ms DOWN, 14 ms Pause")
        print()
        print("Button 3:")
        print("  Hold -> MIDDLE (BTN_MIDDLE)")
        print("  2 ms DOWN, 14 ms Pause")
        print()
        print("ESC:")
        print("  EMERGENCY STOP + program exit")
        print()
        print("F12:")
        print("  Normal program exit")
        print()
        print("=" * 65)
        print()

        # ====================================================
        # MAIN LOOP
        # ====================================================

        while not stop_event.is_set():

            if keyboard.is_pressed("f12"):
                normal_exit(handle)
                break

            time.sleep(0.01)

    except KeyboardInterrupt:

        print("\nProgram terminated by KeyboardInterrupt.")
        stop_event.set()
        f9_active.clear()
        side1_active.clear()
        side2_active.clear()
        side3_active.clear()

    except Exception as e:

        print(f"\nUNEXPECTED ERROR:\n{e}")
        stop_event.set()
        f9_active.clear()
        side1_active.clear()
        side2_active.clear()
        side3_active.clear()

    finally:

        print("\nPerforming safety cleanup...")

        stop_event.set()
        f9_active.clear()
        side1_active.clear()
        side2_active.clear()
        side3_active.clear()

        try:
            keyboard.unhook_all()
            print("Keyboard hooks removed.")
        except Exception as e:
            print(f"Error removing keyboard hooks: {e}")

        # Let workers terminate
        if f9_thread is not None:
            f9_thread.join(timeout=1.0)
        
        if side1_thread is not None:
            side1_thread.join(timeout=1.0)
            
        if side2_thread is not None:
            side2_thread.join(timeout=1.0)
            
        if side3_thread is not None:
            side3_thread.join(timeout=1.0)

        # Release buttons
        if handle is not None:
            try:
                release_all_buttons(handle)
            except Exception as e:
                print(f"Error during safety cleanup: {e}")

        # Close device
        if handle is not None:
            try:
                kernel32.CloseHandle(handle)
                print("Device closed.")
            except Exception as e:
                print(f"Error closing device: {e}")

        print("\nProgram completely terminated.")


# ============================================================
# PROGRAM START
# ============================================================

if __name__ == "__main__":
    main()