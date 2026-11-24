# Blackout
A tool that puts up a black screen on all monitors that doesn't currently have fullscreen/maximized content on it.\
Basically made for when you're watching a movie on one display and don't want the other displays to be distracting.

I personally run it with pythonw from a vbs script to make it a simple click to toggle it on without any windows opening up.

```
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """pythonw"" ""T:\ToolsProgramFiles\Blackout\blackout.py""", 0, False
```

This project only exists because I got annoyed with opening up 2 black png's to cover my other monitors...
And also, it's basically 99% made with Hermes + local Qwen3.8 27B cause I got stuff to do, and why spend a bunch of time learning and developing as a person when you can just slop things in to existance with an agent?\
I don't necessarily like that it succeeded and made something I actually want to use but oh well... Humans might still be useful in the future right? right?
