import os
import json
import subprocess
import platform
import tkinter as tk

from theme import (XP_WINDOW_BG, XP_FIELD_BG, FONT_UI, FONT_UI_BOLD, FONT_MONO,
                    XP_OK_GREEN, XP_WARN_ORANGE, XP_ALERT_RED,
                    make_titlebar, etched_panel, xp_button)

windows_user = os.getlogin()
