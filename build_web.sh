#!/bin/bash
# Build Flutter web app from the included project

cd plant_lab_simulator
flutter build web --release

# Copy to Flask templates
cp -r build/web/* ../app/templates/

echo "✅ Flutter app built and deployed to Flask"
