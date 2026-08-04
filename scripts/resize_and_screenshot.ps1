Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$sig = @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinTop {
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc f, IntPtr l);
    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int ht, bool r);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")]
    public static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr h, IntPtr hAfter, int x, int y, int cx, int cy, uint flags);
    public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
Add-Type -TypeDefinition $sig

$HWND_TOPMOST = [IntPtr](-1)
$SWP_SHOWWINDOW = 0x0040

$script:hwnd = [IntPtr]::Zero
[WinTop]::EnumWindows({
    param($h, $l)
    $sb = New-Object System.Text.StringBuilder(256)
    [WinTop]::GetWindowText($h, $sb, 256)
    if ($sb.ToString() -eq "Audio Factory") { $script:hwnd = $h; return $false }
    return $true
}, [IntPtr]::Zero)

if ($script:hwnd -ne [IntPtr]::Zero) {
    # Restore and bring to front
    [WinTop]::ShowWindow($script:hwnd, 9)   # SW_RESTORE
    # Force topmost + move to primary screen
    [WinTop]::SetWindowPos($script:hwnd, $HWND_TOPMOST, 40, 20, 1160, 1090, $SWP_SHOWWINDOW)
    [WinTop]::SetForegroundWindow($script:hwnd)
    [WinTop]::BringWindowToTop($script:hwnd)
    
    Write-Host "Window forced to top, waiting 1.5s..."
    Start-Sleep -Milliseconds 1500
    
    # Screenshot
    $bmp = New-Object System.Drawing.Bitmap(2560, 1440)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
    
    # Crop at (35,15) 1170x1100
    $cropRect = New-Object System.Drawing.Rectangle(35, 15, 1170, 1100)
    $cropped = $bmp.Clone($cropRect, $bmp.PixelFormat)
    $out = 'C:\Users\lucng\.gemini\antigravity-ide\brain\8b9862ec-a981-441a-94ce-113c4139cefd\app_full.png'
    $cropped.Save($out)
    $cropped.Dispose()
    $g.Dispose()
    $bmp.Dispose()
    
    # Restore non-topmost after capture
    $HWND_NOTOPMOST = [IntPtr](-2)
    [WinTop]::SetWindowPos($script:hwnd, $HWND_NOTOPMOST, 40, 20, 1160, 1090, $SWP_SHOWWINDOW)
    Write-Host "Saved: $out"
} else {
    Write-Host "Audio Factory window not found"
}
