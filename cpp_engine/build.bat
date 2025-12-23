@echo off
REM Build script for Windows

echo Building Pokemon TCG Engine (C++)...
echo.

REM Create build directory
if not exist build mkdir build
cd build

REM Configure with CMake
echo [1/3] Configuring...
cmake -G "Visual Studio 17 2022" -A x64 -DCMAKE_BUILD_TYPE=Release -DBUILD_PYTHON_BINDINGS=ON ..

if errorlevel 1 (
    echo Configuration failed!
    exit /b 1
)

REM Build
echo.
echo [2/3] Building...
cmake --build . --config Release --parallel

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
