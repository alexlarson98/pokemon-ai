@echo off
REM Build script for Windows

echo Building Pokemon TCG Engine (C++)...
echo.

REM Find CMake
set CMAKE_EXE=cmake
where cmake >nul 2>nul
if errorlevel 1 (
    if exist "C:\Program Files\CMake\bin\cmake.exe" (
        set CMAKE_EXE="C:\Program Files\CMake\bin\cmake.exe"
    ) else if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe" (
        set CMAKE_EXE="C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
    ) else (
        echo ERROR: CMake not found. Install from https://cmake.org/download/
        exit /b 1
    )
)

REM Clean and create build directory
if exist build rmdir /s /q build
mkdir build
cd build

REM Configure with CMake - try VS 2019 first (since that's what's installed)
echo [1/3] Configuring...
%CMAKE_EXE% -G "Visual Studio 16 2019" -A x64 -DCMAKE_BUILD_TYPE=Release -DBUILD_PYTHON_BINDINGS=ON ..

if errorlevel 1 (
    echo Configuration failed!
    exit /b 1
)

REM Build
echo.
echo [2/3] Building...
%CMAKE_EXE% --build . --config Release --parallel

if errorlevel 1 (
    echo Build failed!
    exit /b 1
)

REM Copy Python module
echo.
echo [3/3] Installing Python module...
copy /Y lib\Release\pokemon_engine_cpp*.pyd ..\..\ 2>nul
copy /Y lib\pokemon_engine_cpp*.pyd ..\..\ 2>nul

echo.
echo Build complete!
echo Python module: pokemon_engine_cpp.pyd

cd ..
