# Packaging

1. Put a Windows Tesseract distribution in `vendor/tesseract/`.
2. The folder must contain `tesseract.exe`, its DLL files, and `tessdata/eng.traineddata`.
3. Install the development dependencies and run `scripts/build.ps1`.
4. Test `dist/ScreenTranslator/ScreenTranslator.exe` on a clean Windows machine.
5. Zip the `dist/ScreenTranslator` folder for portable distribution, or open
   `ScreenTranslator.iss` with Inno Setup to create an installer.

The end user's machine does not need Python, PyInstaller, or a separate
Tesseract installation once the vendor folder is included in the build.

For a development-only build without bundled OCR, use scripts/build.ps1 -AllowExternalTesseract; do not use that mode for release packages.
