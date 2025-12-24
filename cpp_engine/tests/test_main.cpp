/**
 * Pokemon TCG Engine - Test Runner
 *
 * Simple assert-based test framework for C++ engine.
 * Run with: ./tests/test_runner (after building)
 */

#include <iostream>
#include <vector>
#include <string>
#include <functional>
#include <chrono>

// Test result tracking
struct TestResult {
    std::string name;
    bool passed;
    std::string message;
    double duration_ms;
};

static std::vector<TestResult> g_results;
static int g_tests_run = 0;
static int g_tests_passed = 0;
static int g_tests_failed = 0;

// ============================================================================
// TEST MACROS
// ============================================================================

#define TEST_ASSERT(condition) \
    do { \
        if (!(condition)) { \
            throw std::runtime_error("Assertion failed: " #condition); \
        } \
    } while (0)

#define TEST_ASSERT_MSG(condition, msg) \
    do { \
        if (!(condition)) { \
            throw std::runtime_error(std::string("Assertion failed: ") + msg); \
        } \
    } while (0)

#define TEST_ASSERT_EQ(expected, actual) \
    do { \
        if ((expected) != (actual)) { \
            std::ostringstream oss; \
            oss << "Expected " << (expected) << " but got " << (actual); \
            throw std::runtime_error(oss.str()); \
        } \
    } while (0)

#define TEST_ASSERT_NE(val1, val2) \
    do { \
        if ((val1) == (val2)) { \
            throw std::runtime_error("Expected values to be different"); \
        } \
    } while (0)

#define TEST_ASSERT_TRUE(condition) TEST_ASSERT(condition)
#define TEST_ASSERT_FALSE(condition) TEST_ASSERT(!(condition))
#define TEST_ASSERT_NULL(ptr) TEST_ASSERT((ptr) == nullptr)
#define TEST_ASSERT_NOT_NULL(ptr) TEST_ASSERT((ptr) != nullptr)

// ============================================================================
// TEST REGISTRATION
// ============================================================================

using TestFunc = std::function<void()>;

struct TestCase {
    std::string name;
    std::string suite;
    TestFunc func;
};

static std::vector<TestCase> g_tests;

class TestRegistrar {
public:
    TestRegistrar(const std::string& suite, const std::string& name, TestFunc func) {
        g_tests.push_back({name, suite, func});
    }
};

#define TEST(suite, name) \
    void test_##suite##_##name(); \
    static TestRegistrar g_registrar_##suite##_##name(#suite, #name, test_##suite##_##name); \
    void test_##suite##_##name()

// ============================================================================
// TEST RUNNER
// ============================================================================

void run_test(const TestCase& test) {
    g_tests_run++;

    auto start = std::chrono::high_resolution_clock::now();

    TestResult result;
    result.name = test.suite + "::" + test.name;

    try {
        test.func();
        result.passed = true;
        result.message = "OK";
        g_tests_passed++;
        std::cout << "  [PASS] " << result.name << "\n";
    } catch (const std::exception& e) {
        result.passed = false;
        result.message = e.what();
        g_tests_failed++;
        std::cout << "  [FAIL] " << result.name << "\n";
        std::cout << "         " << result.message << "\n";
    } catch (...) {
        result.passed = false;
        result.message = "Unknown exception";
        g_tests_failed++;
        std::cout << "  [FAIL] " << result.name << "\n";
        std::cout << "         Unknown exception\n";
    }

    auto end = std::chrono::high_resolution_clock::now();
    result.duration_ms = std::chrono::duration<double, std::milli>(end - start).count();

    g_results.push_back(result);
}

void run_all_tests() {
    std::cout << "\n=== Pokemon TCG Engine Tests ===\n\n";

    std::string current_suite;

    for (const auto& test : g_tests) {
        if (test.suite != current_suite) {
            current_suite = test.suite;
            std::cout << "[" << current_suite << "]\n";
        }
        run_test(test);
    }

    std::cout << "\n=== Summary ===\n";
    std::cout << "Total:  " << g_tests_run << "\n";
    std::cout << "Passed: " << g_tests_passed << "\n";
    std::cout << "Failed: " << g_tests_failed << "\n";

    if (g_tests_failed > 0) {
        std::cout << "\nFailed tests:\n";
        for (const auto& result : g_results) {
            if (!result.passed) {
                std::cout << "  - " << result.name << ": " << result.message << "\n";
            }
        }
    }

    std::cout << "\n";
}

void run_tests_matching(const std::string& pattern) {
    std::cout << "\n=== Running tests matching '" << pattern << "' ===\n\n";

    for (const auto& test : g_tests) {
        std::string full_name = test.suite + "::" + test.name;
        if (full_name.find(pattern) != std::string::npos ||
            test.suite.find(pattern) != std::string::npos ||
            test.name.find(pattern) != std::string::npos) {
            run_test(test);
        }
    }

    std::cout << "\n=== Summary ===\n";
    std::cout << "Total:  " << g_tests_run << "\n";
    std::cout << "Passed: " << g_tests_passed << "\n";
    std::cout << "Failed: " << g_tests_failed << "\n\n";
}

// ============================================================================
// MAIN
// ============================================================================

// Forward declare test files (they register via static initializers)
// Include test files here
#include "test_effect_builders.cpp"
#include "test_trainers.cpp"

int main(int argc, char* argv[]) {
    if (argc > 1) {
        // Run specific test pattern
        run_tests_matching(argv[1]);
    } else {
        // Run all tests
        run_all_tests();
    }

    return g_tests_failed > 0 ? 1 : 0;
}
