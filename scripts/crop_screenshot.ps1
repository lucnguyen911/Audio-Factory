Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Focus {
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hwnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr hwnd, int x, int y, int w, int h, bool repaint);
}
"@
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class Win32Find {
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc f, IntPtr l);
    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr h, out RECT r);
    public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

# Find and move Audio Factory to primary screen center
$targetHwnd = [IntPtr]::Zero
[Win32Find]::EnumWindows({
    param($h, $l)
    $sb = New-Object System.Text.StringBuilder(256)
    [Win32Find]::GetWindowText($h, $sb, 256)
    if ($sb.ToString() -eq "Audio Factory") {
        $script:targetHwnd = $h
        return $false
    }
    return $true
}, [IntPtr]::Zero)

if ($script:targetHwnd -ne [IntPtr]::Zero) {
    # Move to primary screen at (100, 100), size 1200x900
    [Win32Focus]::ShowWindow($script:targetHwnd, 9)  # SW_RESTORE
    [Win32Focus]::MoveWindow($script:targetHwnd, 100, 100, 1200, 900, $true)
    [Win32Focus]::SetForegroundWindow($script:targetHwnd)
    Start-Sleep -Milliseconds 600
    Write-Host "Window moved and restored"
    
    # Now screenshot
    $primary = [System.Windows.Forms.Screen]::PrimaryScreen
    $bmp = New-Object System.Drawing.Bitmap($primary.Bounds.Width, $primary.Bounds.Height)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
    
    # Crop: window moved to (100,100) size 1200x900
    $cropRect = New-Object System.Drawing.Rectangle(95, 95, 1210, 910)
    $cropped = $bmp.Clone($cropRect, $bmp.PixelFormat)
    $out = 'C:\Users\lucng\.gemini\antigravity-ide\brain\8b9862ec-a981-441a-94ce-113c4139cefd\app_window.png'
    $cropped.Save($out)
    $cropped.Dispose()
    $g.Dispose()
    $bmp.Dispose()
    Write-Host "Screenshot saved: $out"
} else {
    Write-Host "Window not found"
}
