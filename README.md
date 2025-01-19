# BlueDucky-In-NetHunter
CVE-2023-45866 - BluetoothDucky implementation (Using DuckyScript)


Still have to adjust for ALL ducky related wording/terms but limited on devices for testing.

```bash
REM this is just a comment
string test123
ENTER
```

That should type in test123 in a text field and then press ENTER. 


Setup 
  ```
  curl -sSL https://raw.githubusercontent.com/eirkkk/BlueDucky-In-NetHunter/main/setup | bash
  ```

## Example Usage
```
sudo python3 BluetoothDucky.py 
```

It will look for a payload.txt file in the same directory which can just be ducky script - try something simple provided in this repo to start.


### Other ideas
Implement a step function to check the last letter of the payload line sent, so we can resend/continue from there on failure rather than the entire line

- Might consider making a custom mac vendor lookup for shortcuts on exact devices etc
```bash
Galaxy A14/SM-A14F

GUI + D (desktop)
GUI + E (Email)
GUI + F (FIND)
GUI + H (Samsung audio?)
GUI + K (calendar)
GUI + M (Map)
GUI + N (Notifications)
GUI + T (Music?)
GUI + Q (Full notifications)
GUI + R (Recent files)
GUI + S (messages?)
GUI + U (Accessibility)
GUI + V (volume)
GUI + Z (Settings)
ALT + A (App drawer)

Alt + Space (Search)
```
