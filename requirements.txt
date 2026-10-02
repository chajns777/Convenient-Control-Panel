psutil>=5.9
matplotlib>=3.7

# Windows-only, optional: enables real BIOS-via-WMI and live Windows Update checks.
# The app runs without these — it just shows those two fields as "unavailable" instead.

pywin32>=306; platform_system == "Windows"
wmi>=1.5.1; platform_system == "Windows"
