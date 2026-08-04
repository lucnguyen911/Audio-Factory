Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$primary = [System.Windows.Forms.Screen]::PrimaryScreen
$bmp = New-Object System.Drawing.Bitmap($primary.Bounds.Width, $primary.Bounds.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)

# Full window including bottom buttons - window at (100,100) size 1200x900
# But need to scroll to see bottom - just capture more height
$cropRect = New-Object System.Drawing.Rectangle(95, 95, 1210, 960)
$cropped = $bmp.Clone($cropRect, $bmp.PixelFormat)
$out = 'C:\Users\lucng\.gemini\antigravity-ide\brain\8b9862ec-a981-441a-94ce-113c4139cefd\app_full.png'
$cropped.Save($out)
$cropped.Dispose()
$g.Dispose()
$bmp.Dispose()
Write-Host "Full window saved: $out"
