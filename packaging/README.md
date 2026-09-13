# Windows packaging

Packaging is driven from the project root with:

~~~powershell
.\scripts\package.ps1
~~~

The script:

1. Synchronizes the development environment through uv when available.
2. Builds the PyInstaller directory with the bundled Tesseract runtime.
3. Builds a self-contained PyInstaller single-file executable.
4. Compiles packaging\ScreenTranslator.iss with Inno Setup 6.
5. Creates a portable ZIP from the same PyInstaller directory.

The directory build also verifies that the QtCore, PySide6, Shiboken,
Python runtime, and VC runtime required by the frozen application are present
before packaging continues. It removes the incompatible version-suffixed ICU
DLLs shipped in the PySide6 wheel so Qt uses the Windows 10/11 ICU ABI.

Outputs are written to:

~~~text
dist\ScreenTranslator\
dist\ScreenTranslator-Standalone-v<version>.exe
dist\installer\ScreenTranslator-Setup-v<version>.exe
dist\portable\ScreenTranslator-Portable-v<version>.zip
~~~

The release build requires:

~~~text
vendor\tesseract\tesseract.exe
vendor\tesseract\tessdata\eng.traineddata
~~~

For a development-only build that expects Tesseract to be installed
separately, use:

~~~powershell
.\scripts\package.ps1 -AllowExternalTesseract
~~~

Test the PyInstaller directory and the installer on a clean Windows machine
before publishing. The installer is per-user by default and supports a custom
installation directory.
