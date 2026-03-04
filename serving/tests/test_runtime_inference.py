"""Tests for runtime tool inference from work item text."""

import pytest

from services.runtime_inference import infer_runtime_tools


class TestNodeJsInference:
    def test_react(self):
        tools = infer_runtime_tools("Build React frontend", "Create a React app with components")
        assert "runtime:node" in tools

    def test_vite(self):
        tools = infer_runtime_tools("Scaffold with Vite", "Use Vite to scaffold a new project")
        assert "runtime:node" in tools

    def test_nextjs(self):
        tools = infer_runtime_tools("Add Next.js SSR", "Implement server-side rendering with Next.js")
        assert "runtime:node" in tools

    def test_npm(self):
        tools = infer_runtime_tools("Install deps", "Run npm install to set up the project")
        assert "runtime:node" in tools

    def test_package_json(self):
        tools = infer_runtime_tools("Update deps", "Modify package.json to add lodash")
        assert "runtime:node" in tools

    def test_express(self):
        tools = infer_runtime_tools("Create API server", "Build an Express HTTP server")
        assert "runtime:node" in tools


class TestPythonInference:
    def test_django(self):
        tools = infer_runtime_tools("Build Django app", "Create a Django REST API")
        assert "runtime:python" in tools

    def test_flask(self):
        tools = infer_runtime_tools("Flask service", "Build a Flask microservice")
        assert "runtime:python" in tools

    def test_fastapi(self):
        tools = infer_runtime_tools("API endpoint", "Add FastAPI endpoint for users")
        assert "runtime:python" in tools

    def test_pip_install(self):
        tools = infer_runtime_tools("Install packages", "Run pip install -r requirements.txt")
        assert "runtime:python" in tools

    def test_pytest(self):
        tools = infer_runtime_tools("Add tests", "Write pytest unit tests for the service")
        assert "runtime:python" in tools


class TestGoInference:
    def test_go_module(self):
        tools = infer_runtime_tools("Init Go service", "Create a new Go module for the worker")
        assert "runtime:go" in tools

    def test_go_build(self):
        tools = infer_runtime_tools("Build binary", "Run go build to compile the service")
        assert "runtime:go" in tools

    def test_golang(self):
        tools = infer_runtime_tools("Golang service", "Implement the golang backend service")
        assert "runtime:go" in tools


class TestRustInference:
    def test_cargo(self):
        tools = infer_runtime_tools("Build Rust tool", "Use cargo to build the CLI tool")
        assert "runtime:rust" in tools

    def test_rust(self):
        tools = infer_runtime_tools("Rust implementation", "Implement the parser in Rust")
        assert "runtime:rust" in tools


class TestJavaInference:
    def test_maven(self):
        tools = infer_runtime_tools("Build Java service", "Set up Maven project structure")
        assert "runtime:java" in tools

    def test_spring_boot(self):
        tools = infer_runtime_tools("Spring Boot API", "Create a Spring Boot REST API")
        assert "runtime:java" in tools

    def test_gradle(self):
        tools = infer_runtime_tools("Configure build", "Set up Gradle for the project")
        assert "runtime:java" in tools


class TestNoMatch:
    def test_ambiguous_description(self):
        tools = infer_runtime_tools("Update README", "Fix typos in documentation")
        assert tools == []

    def test_generic_work(self):
        tools = infer_runtime_tools("Design system architecture", "Plan the new microservices layout")
        assert tools == []

    def test_empty_input(self):
        tools = infer_runtime_tools("", "")
        assert tools == []


class TestMultipleRuntimes:
    def test_node_and_python(self):
        tools = infer_runtime_tools(
            "Full-stack app",
            "Build React frontend with FastAPI backend"
        )
        assert "runtime:node" in tools
        assert "runtime:python" in tools


class TestDeduplication:
    def test_no_duplicates_from_multiple_keywords(self):
        tools = infer_runtime_tools(
            "React Vite app",
            "Scaffold a React app using Vite with npm"
        )
        assert tools.count("runtime:node") == 1
