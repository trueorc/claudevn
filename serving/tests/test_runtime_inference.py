"""Tests for runtime tool inference from work item text.

The inference should only match when the task needs to EXECUTE a dev tool
(scaffold, build, install, test, run). Writing code in a framework does NOT
require the runtime.
"""

import pytest

from services.runtime_inference import infer_runtime_tools


class TestNodeJsExecution:
    """Tasks that need to execute Node.js tools → runtime:node."""

    def test_npm_install(self):
        tools = infer_runtime_tools("Install deps", "Run npm install to set up the project")
        assert "runtime:node" in tools

    def test_npx_scaffold(self):
        tools = infer_runtime_tools("Scaffold app", "Run npx create-react-app my-blog")
        assert "runtime:node" in tools

    def test_npm_run_build(self):
        tools = infer_runtime_tools("Build frontend", "Run npm run build for production")
        assert "runtime:node" in tools

    def test_npm_test(self):
        tools = infer_runtime_tools("Run tests", "Execute npm test to verify components")
        assert "runtime:node" in tools

    def test_package_json(self):
        tools = infer_runtime_tools("Update deps", "Modify package.json to add lodash")
        assert "runtime:node" in tools

    def test_yarn_install(self):
        tools = infer_runtime_tools("Setup", "Run yarn install to bootstrap the project")
        assert "runtime:node" in tools

    def test_create_react_app(self):
        tools = infer_runtime_tools("Bootstrap project", "Use create-react-app to scaffold")
        assert "runtime:node" in tools


class TestNodeJsCodeGenNoMatch:
    """Tasks that only write code in JS/React → no runtime needed."""

    def test_react_component(self):
        tools = infer_runtime_tools("Build React frontend", "Create a React app with components")
        assert tools == []

    def test_express_endpoint(self):
        tools = infer_runtime_tools("Create API server", "Build an Express HTTP server")
        assert tools == []

    def test_nextjs_page(self):
        tools = infer_runtime_tools("Add Next.js SSR", "Implement server-side rendering with Next.js")
        assert tools == []

    def test_vite_config(self):
        tools = infer_runtime_tools("Configure Vite", "Write Vite configuration for the project")
        assert tools == []

    def test_blog_file_storage(self):
        tools = infer_runtime_tools("Blog file storage service", "Implement file storage for blog posts")
        assert tools == []


class TestPythonExecution:
    """Tasks that need to execute Python tools → runtime:python."""

    def test_pip_install(self):
        tools = infer_runtime_tools("Install packages", "Run pip install -r requirements.txt")
        assert "runtime:python" in tools

    def test_pytest(self):
        tools = infer_runtime_tools("Add tests", "Write pytest unit tests for the service")
        assert "runtime:python" in tools

    def test_requirements_txt(self):
        tools = infer_runtime_tools("Setup deps", "Create requirements.txt with all dependencies")
        assert "runtime:python" in tools

    def test_uvicorn(self):
        tools = infer_runtime_tools("Start server", "Run uvicorn to start the API server")
        assert "runtime:python" in tools

    def test_django_admin(self):
        tools = infer_runtime_tools("Scaffold project", "Run django-admin startproject myapp")
        assert "runtime:python" in tools


class TestPythonCodeGenNoMatch:
    """Tasks that only write Python code → no runtime needed."""

    def test_django_view(self):
        tools = infer_runtime_tools("Build Django app", "Create a Django REST API view")
        assert tools == []

    def test_flask_endpoint(self):
        tools = infer_runtime_tools("Flask service", "Build a Flask microservice endpoint")
        assert tools == []

    def test_fastapi_endpoint(self):
        tools = infer_runtime_tools("API endpoint", "Add FastAPI endpoint for users")
        assert tools == []


class TestGoExecution:
    """Tasks that need to execute Go tools → runtime:go."""

    def test_go_build(self):
        tools = infer_runtime_tools("Build binary", "Run go build to compile the service")
        assert "runtime:go" in tools

    def test_go_test(self):
        tools = infer_runtime_tools("Run tests", "Run go test ./... to verify")
        assert "runtime:go" in tools

    def test_go_mod(self):
        tools = infer_runtime_tools("Init module", "Run go mod init for the new service")
        assert "runtime:go" in tools


class TestGoCodeGenNoMatch:
    """Tasks that only write Go code → no runtime needed."""

    def test_golang_service(self):
        tools = infer_runtime_tools("Golang service", "Implement the golang backend service")
        assert tools == []

    def test_go_handler(self):
        tools = infer_runtime_tools("Add handler", "Create Go HTTP handler functions")
        assert tools == []


class TestRustExecution:
    def test_cargo_build(self):
        tools = infer_runtime_tools("Build Rust tool", "Use cargo build to compile the CLI tool")
        assert "runtime:rust" in tools

    def test_cargo_test(self):
        tools = infer_runtime_tools("Test parser", "Run cargo test to verify the parser")
        assert "runtime:rust" in tools

    def test_rustc(self):
        tools = infer_runtime_tools("Compile", "Use rustc to compile the binary")
        assert "runtime:rust" in tools


class TestRustCodeGenNoMatch:
    def test_rust_implementation(self):
        tools = infer_runtime_tools("Rust implementation", "Implement the parser in Rust")
        assert tools == []


class TestJavaExecution:
    def test_maven(self):
        tools = infer_runtime_tools("Build Java service", "Set up Maven project with mvn archetype")
        assert "runtime:java" in tools

    def test_gradle_build(self):
        tools = infer_runtime_tools("Build project", "Run gradle build for the service")
        assert "runtime:java" in tools

    def test_pom_xml(self):
        tools = infer_runtime_tools("Configure build", "Update pom.xml with new dependencies")
        assert "runtime:java" in tools


class TestJavaCodeGenNoMatch:
    def test_spring_boot_code(self):
        tools = infer_runtime_tools("Spring Boot API", "Create a Spring Boot REST controller")
        assert tools == []

    def test_java_class(self):
        tools = infer_runtime_tools("Add service", "Implement the Java UserService class")
        assert tools == []


class TestFalsePositiveRegression:
    """Ensure substring collisions don't cause false positives."""

    def test_go_model_not_go_mod(self):
        tools = infer_runtime_tools("Data model", "Create a Go model for users")
        assert tools == []

    def test_go_moderate_not_go_mod(self):
        tools = infer_runtime_tools("Content moderation", "Go moderate the content queue")
        assert tools == []

    def test_npm_runtime_not_npm_run(self):
        tools = infer_runtime_tools("Architecture", "Describe the npm runtime environment")
        assert tools == []


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
    def test_node_and_python_execution(self):
        tools = infer_runtime_tools(
            "Full-stack setup",
            "Run npm install for frontend and pip install for backend"
        )
        assert "runtime:node" in tools
        assert "runtime:python" in tools

    def test_mixed_codegen_and_execution(self):
        """Execution keywords match, framework-only mentions don't."""
        tools = infer_runtime_tools(
            "Full-stack app",
            "Build React frontend with FastAPI backend"
        )
        assert tools == []


class TestDeduplication:
    def test_no_duplicates_from_multiple_keywords(self):
        tools = infer_runtime_tools(
            "Setup project",
            "Run npm install then npm run build to scaffold"
        )
        assert tools.count("runtime:node") == 1
