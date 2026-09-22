# nikke_M61-Vulcan


>[!WARNING]
>I am not a programmer. This project was created with the assistance of AI. The code may contain errors, bugs, or unexpected behavior. Please review and use it at your own discretion.

>[!CAUTION]
>This software is provided "as is", without warranty of any kind.
>Use it at your own risk. The author is not responsible for any damage, data loss, system issues, account restrictions, or other consequences resulting from the use or misuse of this software.

>[!CAUTION]
>Using this tool in online games may result in a permanent ban.
>The use of this tool may violate the Terms of Service, rules, or anti-cheat policies of certain online games. As a result, your account may be permanently banned or otherwise restricted. Use this tool at your own risk. The author is not responsible for any bans, suspensions, account restrictions, or other consequences resulting from its use.


## **Requirements**

- **Windows**
- The latest version of **Python**
- **Logitech G HUB** must be installed, as the tool requires its virtual HID driver.
- A Logitech mouse with configurable side buttons is required.
  - Tested with a **Logitech G502 HERO**

### **1. Verify the Virtual Mouse Driver**

Open **Device Manager** and navigate to:

**Human Interface Devices**

Check whether the following device is listed:

`Logitech G HUB Virtual Mouse`

If the device is **not** present, navigate to:

`C:\ProgramData\LGHUB\depots\869589\driver_hid_virtual`

and run:

`virtual_driver_manager.exe`

Afterwards, check **Human Interface Devices** again and verify that **Logitech G HUB Virtual Mouse** is listed.

### **2. Install the Tool**

Once the virtual driver has been successfully installed, download the latest `python.exe` from the **Releases** section.

> [!CAUTION]
> **The executable must be run as Administrator.**
>
> Administrator privileges are required for the tool to communicate with the virtual HID device.


---

## **Setup & Usage**

### **Burst Controls**

Configure your mouse controls accordingly.

Your control scheme for the burst inputs should look **exactly like this**:

<img width="594" height="445" alt="Burst control configuration" src="https://github.com/user-attachments/assets/2a743de4-0317-4d21-aa60-4d75db60d925" />


The following keyboard inputs are used:

| Key | Action |
|---|---|
| `1` | Trigger Burst 1 |
| `2` | Trigger Burst 2 |
| `3` | Trigger Burst 3 |
| `C` | Trigger Charged Shot |
| `ESC` | Emergency Stop |
| `F12` | Exit the application |

### **Charged Shot**

Holding the **`C`** key triggers the charged shot.

Timing is currently hard-coded:

- **200 ms** charge time
- **20 ms** input buffer

### **Burst Timing**

Keys **`1`**, **`2`**, and **`3`** trigger their corresponding burst.

Timing is currently hard-coded to:

- **2 ms** click duration
- **14 ms** delay between inputs

This is intended to maintain a consistent **~16 ms input cycle**, corresponding to approximately **60 FPS**.

> [!NOTE]
> The timing values are hard-coded and are not configurable through the application.


---

## **Simultaneous Inputs**

When multiple trigger keys are held at the same time, the order in which their inputs are processed is **not guaranteed**.

For example, if you press and hold **`1`** and then press and hold **`2`**, the game is **not guaranteed to receive the input from `1` first** simply because `1` was pressed first.

When multiple inputs are active simultaneously, their processing order depends on how the operating system, input handling, and the application process the events. As a result, the order may vary between executions.

The tool combines simultaneous button states into a single HID report where possible, rather than intentionally prioritizing one input over another.

> [!IMPORTANT]
> **Do not rely on a specific input order when using multiple trigger keys simultaneously.**
>
> If two or more inputs occur at effectively the same time, the resulting order is **not deterministic**.


---
# **Technical Details**

## **Overview**

The application is a Python-based input simulation tool that communicates with a virtual HID mouse device through the Logitech G HUB virtual HID driver.

Instead of using the standard Windows mouse input APIs, the application communicates with the virtual device interface using **IOCTL** requests and sends **7-byte HID mouse reports**.

The application supports four independently triggered mouse inputs:

- **Left Click**
- **Middle Click**
- **XButton1**
- **XButton2**

Input timing is controlled at millisecond resolution and can be configured in the source code.

---

## **Input & Timing**

The application uses `time.perf_counter()` for high-resolution timing of click durations and delays.

The default burst timing is:

- **2 ms** button press
- **14 ms** delay
- **~16 ms total input cycle**

The application also supports a charged-shot input with a **200 ms charge time** and a **20 ms input buffer**.

Keyboard input is detected globally through keyboard hooks, allowing the application to receive `C`, `1`, `2`, and `3` regardless of which window currently has focus.

---

## **Concurrency**

Each trigger key (`C`, `1`, `2`, `3`) is handled by a dedicated worker thread.

Worker threads remain blocked while inactive and are signaled when their corresponding input becomes active. This avoids continuous polling while waiting for user input.

### **Thread Safety**

Multiple worker threads may attempt to update the mouse state at the same time. To prevent concurrent access to the driver communication layer, the application uses a `threading.Lock` (`button_lock`).

The current button state is maintained as a **bitmask**. When multiple buttons are active simultaneously, their states are combined using bitwise operations.

For example:

````python
0x08 | 0x04
````

---

The resulting state is then written as a single HID report.

This allows multiple button states to be represented within the same report rather than having individual worker threads overwrite each other's state.

## **Global Controls & Failsafes**

The application provides two global control keys:

- **`ESC`** — immediately stops all active input and releases all simulated buttons.
- **`F12`** — gracefully terminates the application.

These controls remain available regardless of which application or window currently has focus.

---

## **Resource Management**

The application uses a `finally` block to ensure that resources are properly released during shutdown.

The cleanup process includes:

1. Stopping and joining all worker threads.
2. Releasing all simulated buttons using `release_all_buttons()`.
3. Closing the device handle using `kernel32.CloseHandle`.

This cleanup is intended to prevent buttons from remaining in a pressed state and to ensure that the virtual device handle is properly released.





