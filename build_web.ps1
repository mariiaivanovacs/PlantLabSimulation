# Build Flutter web app from the included project
cd plant_lab_simulator
flutter build web --release

# Copy to Flask templates
Remove-Item -Path "..\app\templates\*" -Recurse -Force
Copy-Item -Path "build\web\*" -Destination "..\app\templates\" -Recurse -Force

Write-Host "✅ Flutter app built and deployed to Flask" -ForegroundColor Green
