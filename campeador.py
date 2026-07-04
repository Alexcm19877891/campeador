import queue
import threading
import time
import logging
import json
import os
import tkinter as tk
from tkinter import ttk

import numpy as np
import sounddevice as sd
import pyperclip
import pyautogui

from pynput import mouse, keyboard
from faster_whisper import WhisperModel

import pystray
from PIL import Image, ImageDraw, ImageTk


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

MODEL_SIZE = "base"          # Faster: tiny/base. Better: small/medium/large-v3.
DEVICE = "cuda"
COMPUTE_TYPE = "float16"
SAMPLE_RATE = 16000

AUTO_PASTE_DEFAULT = False   # False = copy only. True = copy + paste.

LANGUAGES = {
    "Auto detect": None,
    "Spanish": "es",
    "English": "en",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Portuguese": "pt",
}

OUTPUT_MODES = {
    "Same language": "transcribe",
    "English translation": "translate",
}

PRESET_TRIGGERS = {
    "Mouse Button 4": ("mouse", mouse.Button.x1),
    "Mouse Button 5": ("mouse", mouse.Button.x2),

    "F8": ("key", keyboard.Key.f8),
    "F9": ("key", keyboard.Key.f9),
    "F10": ("key", keyboard.Key.f10),
    "F12": ("key", keyboard.Key.f12),

    "Left Ctrl": ("key", keyboard.Key.ctrl_l),
    "Right Ctrl": ("key", keyboard.Key.ctrl_r),
    "Left Alt": ("key", keyboard.Key.alt_l),
    "Right Alt": ("key", keyboard.Key.alt_r),
}


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logging.basicConfig(
    filename="whisper_ui.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# --------------------------------------------------
# SAVED USER SETTINGS
# --------------------------------------------------

SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "acmw_settings.json",
)

DEFAULT_SETTINGS = {
    "trigger_preset": "Mouse Button 4",
    "source_language": "Spanish",
    "output_mode": "English translation",
    "auto_paste": False,
}


def load_settings():
    settings = DEFAULT_SETTINGS.copy()

    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            if isinstance(loaded, dict):
                settings.update(loaded)

    except Exception as e:
        logging.warning(f"Could not load settings: {e}")

    # Validate settings so a broken/old JSON file never crashes the app.
    if settings.get("trigger_preset") not in PRESET_TRIGGERS:
        settings["trigger_preset"] = DEFAULT_SETTINGS["trigger_preset"]

    if settings.get("source_language") not in LANGUAGES:
        settings["source_language"] = DEFAULT_SETTINGS["source_language"]

    if settings.get("output_mode") not in OUTPUT_MODES:
        settings["output_mode"] = DEFAULT_SETTINGS["output_mode"]

    settings["auto_paste"] = bool(settings.get("auto_paste", False))

    return settings


APP_SETTINGS = load_settings()


# --------------------------------------------------
# GLOBAL STATE
# --------------------------------------------------

audio_queue = queue.Queue()
recording = False
busy = False
stream = None
chunks = []

model = None
mouse_listener = None
keyboard_listener = None
tray_icon = None

state_lock = threading.Lock()

initial_trigger_type, initial_trigger_value = PRESET_TRIGGERS[
    APP_SETTINGS["trigger_preset"]
]

trigger_type = initial_trigger_type
trigger_value = initial_trigger_value
trigger_label = APP_SETTINGS["trigger_preset"]

pressed_trigger = False

source_language_code = LANGUAGES[APP_SETTINGS["source_language"]]
output_task = OUTPUT_MODES[APP_SETTINGS["output_mode"]]
auto_paste_enabled = APP_SETTINGS["auto_paste"]

tk_icon_refs = []
last_tray_color = None
tray_icon_lock = threading.Lock()


# --------------------------------------------------
# SMALL HELPERS
# --------------------------------------------------

def make_tray_icon(color):
    img = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    draw.ellipse((6, 6, 58, 58), fill=color, outline="black", width=3)

    return img


def update_window_icon(color):
    """
    Updates the icon shown in the Windows taskbar/title bar.
    Tkinter needs us to keep a reference to the image, otherwise it can disappear.
    """
    try:
        tk_img = ImageTk.PhotoImage(make_tray_icon(color))
        tk_icon_refs.append(tk_img)

        if len(tk_icon_refs) > 10:
            del tk_icon_refs[:-5]

        root.iconphoto(True, tk_img)

    except Exception as e:
        logging.warning(f"Could not update window icon: {e}")


def update_tray_icon(color):
    """
    Hard-refresh system tray icon near the Windows clock.
    This removes/re-adds the tray icon because Windows sometimes caches pystray icons.
    """
    global last_tray_color

    try:
        if tray_icon is None:
            return

        with tray_icon_lock:
            if last_tray_color == color:
                return

            last_tray_color = color

            new_img = make_tray_icon(color)

            tray_icon.icon = new_img
            tray_icon.title = f"Campeador - {color.upper()}"

            try:
                tray_icon.visible = False
                time.sleep(0.05)
                tray_icon.visible = True
            except Exception as e:
                logging.warning(f"Tray visible refresh failed: {e}")

            logging.info(f"Tray icon hard-refreshed to {color}")

    except Exception as e:
        logging.warning(f"Could not update tray icon: {e}")


def ui_call(fn):
    try:
        root.after(0, fn)
    except Exception:
        pass


def log_event(message):
    logging.info(message)

    def update():
        event_label.config(text=message)

    ui_call(update)


def set_status(text, color):
    def update():
        status_label.config(text=text)
        status_dot.itemconfig(status_circle, fill=color)

        root.title(f"Campeador - {text}")

        update_window_icon(color)
        update_tray_icon(color)

    ui_call(update)


def save_current_settings():
    try:
        data = {
            "trigger_preset": trigger_preset_var.get(),
            "source_language": source_language_var.get(),
            "output_mode": output_mode_var.get(),
            "auto_paste": bool(auto_paste_var.get()),
        }

        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logging.info(f"Settings saved: {data}")

    except Exception as e:
        logging.warning(f"Could not save settings: {e}")


def mouse_button_label(button):
    if button == mouse.Button.x1:
        return "Mouse Button 4"
    if button == mouse.Button.x2:
        return "Mouse Button 5"
    if button == mouse.Button.left:
        return "Left Mouse"
    if button == mouse.Button.right:
        return "Right Mouse"
    if button == mouse.Button.middle:
        return "Middle Mouse"
    return str(button)


def key_label(key):
    if isinstance(key, keyboard.KeyCode):
        if key.char:
            return key.char.upper()
        return str(key)

    return str(key).replace("Key.", "").upper()


def current_trigger_matches(input_type, input_value):
    with state_lock:
        return input_type == trigger_type and input_value == trigger_value


def set_trigger(new_type, new_value, new_label):
    global trigger_type, trigger_value, trigger_label

    with state_lock:
        trigger_type = new_type
        trigger_value = new_value
        trigger_label = new_label

    def update():
        trigger_display_var.set(f"Current trigger: {new_label}")
        event_label.config(text=f"Trigger set to: {new_label}")

    ui_call(update)
    logging.info(f"Trigger set to: {new_type} {new_label}")

    save_current_settings()


def update_language_settings(*args):
    global source_language_code, output_task, auto_paste_enabled

    selected_source = source_language_var.get()
    selected_output = output_mode_var.get()

    with state_lock:
        source_language_code = LANGUAGES[selected_source]
        output_task = OUTPUT_MODES[selected_output]
        auto_paste_enabled = bool(auto_paste_var.get())

    log_event(
        f"Language: {selected_source} → {selected_output}; "
        f"Auto-paste: {'ON' if auto_paste_enabled else 'OFF'}"
    )

    save_current_settings()


def update_trigger_from_preset(*args):
    selected = trigger_preset_var.get()

    if selected in PRESET_TRIGGERS:
        new_type, new_value = PRESET_TRIGGERS[selected]
        set_trigger(new_type, new_value, selected)


# --------------------------------------------------
# WHISPER
# --------------------------------------------------

def load_model():
    global model

    set_status("Loading model...", "orange")
    log_event("Loading Whisper model...")

    try:
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        set_status("Idle", "red")
        log_event(f"Model loaded on {DEVICE}.")

    except Exception as e:
        logging.exception("CUDA failed. Falling back to CPU.")

        model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

        set_status("Idle - CPU fallback", "red")
        log_event(f"CUDA failed. CPU fallback active. Error: {e}")


def audio_callback(indata, frames, time_info, status):
    if status:
        logging.warning(str(status))

    if recording:
        audio_queue.put(indata.copy())


def start_recording():
    global recording, stream, chunks, busy

    if model is None:
        log_event("Model is still loading. Wait a few seconds.")
        return

    if busy or recording:
        return

    chunks = []

    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break

    try:
        recording = True

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=audio_callback,
        )

        stream.start()

        set_status("Recording", "green")
        log_event("Recording... release trigger to stop.")

    except Exception as e:
        recording = False
        set_status("Error", "red")
        log_event(f"Could not start microphone: {e}")
        logging.exception("Microphone error.")


def stop_recording_and_transcribe():
    global recording, stream, chunks, busy

    if not recording:
        return

    recording = False
    busy = True

    set_status("Transcribing...", "orange")
    log_event("Recording stopped. Transcribing...")

    time.sleep(0.15)

    try:
        if stream:
            stream.stop()
            stream.close()
            stream = None

        while not audio_queue.empty():
            chunks.append(audio_queue.get())

        if not chunks:
            set_status("Idle", "red")
            log_event("No audio captured.")
            return

        audio = np.concatenate(chunks, axis=0).flatten()
        duration = len(audio) / SAMPLE_RATE

        log_event(f"Captured {duration:.2f}s audio.")

        if duration < 0.4:
            set_status("Idle", "red")
            log_event("Audio too short. Ignored.")
            return

        with state_lock:
            lang = source_language_code
            task = output_task
            do_auto_paste = auto_paste_enabled

        # Whisper translation means "translate to English".
        # If source is English and output is English, transcribe is cleaner.
        if task == "translate" and lang == "en":
            task = "transcribe"

        start_time = time.time()

        segments, info = model.transcribe(
            audio,
            language=lang,
            task=task,
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
        )

        text = " ".join(segment.text.strip() for segment in segments).strip()
        elapsed = time.time() - start_time

        if not text:
            set_status("Idle", "red")
            log_event("No speech detected.")
            return

        pyperclip.copy(text)

        if do_auto_paste:
            pyautogui.hotkey("ctrl", "v")
            log_event(f"Pasted: {text} ({elapsed:.2f}s)")
        else:
            log_event(f"Copied to clipboard: {text} ({elapsed:.2f}s)")

        set_status("Idle", "red")

    except Exception as e:
        logging.exception("Transcription error.")
        set_status("Error", "red")
        log_event(f"Transcription error: {e}")

    finally:
        busy = False


# --------------------------------------------------
# INPUT LISTENERS
# --------------------------------------------------

def handle_trigger_pressed():
    global pressed_trigger

    if pressed_trigger:
        return

    pressed_trigger = True
    start_recording()


def handle_trigger_released():
    global pressed_trigger

    if not pressed_trigger:
        return

    pressed_trigger = False
    threading.Thread(target=stop_recording_and_transcribe, daemon=True).start()


def on_mouse_click(x, y, button, pressed):
    if not current_trigger_matches("mouse", button):
        return

    if pressed:
        handle_trigger_pressed()
    else:
        handle_trigger_released()


def on_key_press(key):
    if current_trigger_matches("key", key):
        handle_trigger_pressed()


def on_key_release(key):
    if current_trigger_matches("key", key):
        handle_trigger_released()


def start_input_listeners():
    global mouse_listener, keyboard_listener

    mouse_listener = mouse.Listener(on_click=on_mouse_click)
    keyboard_listener = keyboard.Listener(
        on_press=on_key_press,
        on_release=on_key_release,
    )

    mouse_listener.start()
    keyboard_listener.start()

    log_event("Input listeners started.")


# --------------------------------------------------
# TRAY
# --------------------------------------------------

def show_window(icon=None, item=None):
    root.after(0, root.deiconify)
    root.after(0, root.lift)


def hide_to_tray():
    root.withdraw()


def quit_app(icon=None, item=None):
    logging.info("Exiting app.")

    try:
        if mouse_listener:
            mouse_listener.stop()

        if keyboard_listener:
            keyboard_listener.stop()

        if tray_icon:
            tray_icon.stop()

    except Exception:
        pass

    root.after(0, root.destroy)


def setup_tray():
    global tray_icon

    menu = pystray.Menu(
        pystray.MenuItem("Show", show_window),
        pystray.MenuItem("Exit", quit_app),
    )

    tray_icon = pystray.Icon(
        "Campeador",
        make_tray_icon("red"),
        "Campeador - RED",
        menu,
    )

    logging.info("Tray icon started.")
    tray_icon.run()


# --------------------------------------------------
# TKINTER UI
# --------------------------------------------------

root = tk.Tk()
root.title("Campeador")
root.geometry("720x560")
root.minsize(720, 560)
root.resizable(True, True)

main = ttk.Frame(root, padding=20)
main.pack(fill="both", expand=True)

title = ttk.Label(main, text="Campeador", font=("Segoe UI", 16, "bold"))
title.pack(anchor="w")

status_frame = ttk.Frame(main)
status_frame.pack(anchor="w", pady=(12, 8))

status_dot = tk.Canvas(status_frame, width=24, height=24, highlightthickness=0)
status_circle = status_dot.create_oval(4, 4, 20, 20, fill="red")
status_dot.pack(side="left")

status_label = ttk.Label(status_frame, text="Starting...")
status_label.pack(side="left", padx=(8, 0))

event_label = ttk.Label(main, text="Starting app...", wraplength=660)
event_label.pack(anchor="w", pady=(4, 12))

# Trigger section
ttk.Label(main, text="Trigger preset:").pack(anchor="w")

trigger_preset_var = tk.StringVar(value=APP_SETTINGS["trigger_preset"])

trigger_preset_box = ttk.Combobox(
    main,
    textvariable=trigger_preset_var,
    values=list(PRESET_TRIGGERS.keys()),
    state="readonly",
)

trigger_preset_box.pack(fill="x", pady=(2, 6))
trigger_preset_box.bind("<<ComboboxSelected>>", update_trigger_from_preset)

trigger_display_var = tk.StringVar(
    value=f"Current trigger: {APP_SETTINGS['trigger_preset']}"
)

trigger_display = ttk.Label(main, textvariable=trigger_display_var)
trigger_display.pack(anchor="w", pady=(2, 10))

# Language section
lang_frame = ttk.Frame(main)
lang_frame.pack(fill="x", pady=(4, 8))

left_lang = ttk.Frame(lang_frame)
left_lang.pack(side="left", fill="x", expand=True, padx=(0, 8))

right_lang = ttk.Frame(lang_frame)
right_lang.pack(side="right", fill="x", expand=True)

ttk.Label(left_lang, text="Speak language:").pack(anchor="w")

source_language_var = tk.StringVar(value=APP_SETTINGS["source_language"])

source_language_box = ttk.Combobox(
    left_lang,
    textvariable=source_language_var,
    values=list(LANGUAGES.keys()),
    state="readonly",
)

source_language_box.pack(fill="x")
source_language_box.bind("<<ComboboxSelected>>", update_language_settings)

ttk.Label(right_lang, text="Output mode:").pack(anchor="w")

output_mode_var = tk.StringVar(value=APP_SETTINGS["output_mode"])

output_mode_box = ttk.Combobox(
    right_lang,
    textvariable=output_mode_var,
    values=list(OUTPUT_MODES.keys()),
    state="readonly",
)

output_mode_box.pack(fill="x")
output_mode_box.bind("<<ComboboxSelected>>", update_language_settings)

auto_paste_var = tk.BooleanVar(value=APP_SETTINGS["auto_paste"])

auto_paste_check = ttk.Checkbutton(
    main,
    text="Auto-paste result after transcription",
    variable=auto_paste_var,
    command=update_language_settings,
)

auto_paste_check.pack(anchor="w", pady=(16, 16))

buttons = ttk.Frame(main)
buttons.pack(fill="x", pady=(10, 0))

hide_button = ttk.Button(buttons, text="Hide to tray", command=hide_to_tray)
hide_button.pack(side="left")

exit_button = ttk.Button(buttons, text="Exit", command=quit_app)
exit_button.pack(side="right")

root.protocol("WM_DELETE_WINDOW", quit_app)

# Start background systems
threading.Thread(target=setup_tray, daemon=True).start()
threading.Thread(target=load_model, daemon=True).start()

start_input_listeners()
update_language_settings()

root.mainloop()