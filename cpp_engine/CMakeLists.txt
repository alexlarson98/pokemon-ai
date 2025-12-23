cmake_minimum_required(VERSION 3.16)
project(pokemon_engine VERSION 1.0.0 LANGUAGES CXX)

# C++17 required for std::optional, std::variant, structured bindings
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Optimization flags for release
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    if(MSVC)
        set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} /O2 /DNDEBUG")
    else()
        set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -DNDEBUG -march=native")
    endif()
endif()

# Debug flags
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    if(MSVC)
        set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} /Od /Zi")
    else()
        set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -O0 -g -fsanitize=address")
    endif()
endif()

# ============================================================================
# CORE LIBRARY
# ============================================================================

add_library(pokemon_engine_core STATIC
    src/engine.cpp
    src/card_database.cpp
)

target_include_directories(pokemon_engine_core
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
)

# ============================================================================
# PYTHON BINDINGS (optional)
# ============================================================================

option(BUILD_PYTHON_BINDINGS "Build Python bindings with pybind11" ON)

if(BUILD_PYTHON_BINDINGS)
    # Find Python
    find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

    # Find pybind11
    # Try to find installed pybind11, or use FetchContent
    find_package(pybind11 QUIET)

    if(NOT pybind11_FOUND)
        message(STATUS "pybind11 not found, fetching from GitHub...")
        include(FetchContent)
        FetchContent_Declare(
            pybind11
            GIT_REPOSITORY https://github.com/pybind/pybind11.git
            GIT_TAG v2.11.1
        )
        FetchContent_MakeAvailable(pybind11)
    endif()

    # Create Python module
    pybind11_add_module(pokemon_engine_cpp
        bindings/pybind_module.cpp
    )

    target_link_libraries(pokemon_engine_cpp
        PRIVATE
            pokemon_engine_core
    )

    # Set output name and location
    set_target_properties(pokemon_engine_cpp PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
    )

    # Install Python module to site-packages
    install(TARGETS pokemon_engine_cpp
        LIBRARY DESTINATION ${Python3_SITELIB}
    )
endif()

# ============================================================================
# STANDALONE EXECUTABLE (for testing)
# ============================================================================

option(BUILD_STANDALONE "Build standalone test executable" OFF)

if(BUILD_STANDALONE)
    add_executable(pokemon_engine_test
        tests/main.cpp
    )

    target_link_libraries(pokemon_engine_test
        PRIVATE
            pokemon_engine_core
    )
endif()

# ============================================================================
# BENCHMARK (optional)
# ============================================================================

option(BUILD_BENCHMARK "Build benchmark executable" OFF)

if(BUILD_BENCHMARK)
    add_executable(pokemon_benchmark
        benchmark/benchmark.cpp
    )

    target_link_libraries(pokemon_benchmark
        PRIVATE
            pokemon_engine_core
    )
endif()

# ============================================================================
# INSTALLATION
# ============================================================================

install(TARGETS pokemon_engine_core
    EXPORT pokemon_engine_targets
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
    RUNTIME DESTINATION bin
)

install(DIRECTORY include/
    DESTINATION include
)

install(EXPORT pokemon_engine_targets
    FILE pokemon_engine_targets.cmake
    NAMESPACE pokemon::
    DESTINATION lib/cmake/pokemon_engine
)

# ============================================================================
# CONFIGURATION FILE
# ============================================================================

include(CMakePackageConfigHelpers)

configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/pokemon_engine_config.cmake.in"
    "${CMAKE_CURRENT_BINARY_DIR}/pokemon_engine_config.cmake"
    INSTALL_DESTINATION lib/cmake/pokemon_engine
)

write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/pokemon_engine_config_version.cmake"
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)

install(FILES
    "${CMAKE_CURRENT_BINARY_DIR}/pokemon_engine_config.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/pokemon_engine_config_version.cmake"
    DESTINATION lib/cmake/pokemon_engine
)

# ============================================================================
# PRINT CONFIGURATION
# ============================================================================

message(STATUS "")
message(STATUS "Pokemon TCG Engine Configuration:")
message(STATUS "  Version:           ${PROJECT_VERSION}")
message(STATUS "  Build type:        ${CMAKE_BUILD_TYPE}")
message(STATUS "  C++ Standard:      ${CMAKE_CXX_STANDARD}")
message(STATUS "  Python bindings:   ${BUILD_PYTHON_BINDINGS}")
message(STATUS "  Standalone test:   ${BUILD_STANDALONE}")
message(STATUS "  Benchmark:         ${BUILD_BENCHMARK}")
message(STATUS "")
