# Releasing

Publishing uses PyPI trusted publishing, so no API token is stored in the repository or in GitHub
secrets. The trade is a one-time setup on pypi.org that only the project owner can do.

## One-time setup, before the first release

PyPI needs to be told which workflow is allowed to publish. Because `capex-atlas` does not exist on
PyPI yet, this is added as a **pending publisher** rather than against an existing project.

1. Sign in to <https://pypi.org> and open <https://pypi.org/manage/account/publishing/>.
2. Under "Add a new pending publisher", fill in exactly:

   | Field | Value |
   |---|---|
   | PyPI Project Name | `capex-atlas` |
   | Owner | `jman4162` |
   | Repository name | `capex-atlas` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

3. In the GitHub repository, create an environment named `pypi`
   (Settings → Environments → New environment). Adding a required reviewer to it is worth doing: it
   means a compromised build cannot publish without a human approving the step.

Optional dry run: repeat step 2 on <https://test.pypi.org>, then publish there once before the real
upload. Worth doing for a first release, since a version number can never be reused.

## Each release

1. Update the version in `pyproject.toml`. It is the only place it lives; `__version__` reads from
   installed distribution metadata rather than a second literal, so there is nothing to keep in sync.
2. Move the `## Unreleased` entries in `CHANGELOG.md` under the new version with today's date.
3. Rebuild the committed artifacts if anything affecting them changed:

   ```bash
   uv run python scripts/build_example.py
   uv run python scripts/generate_readme_figures.py
   ```

   CI fails if either has drifted, so this is not optional when the engine has moved.
4. Run the gates:

   ```bash
   uv run ruff check . && uv run ruff format --check .
   uv run mypy src/ && uv run lint-imports && uv run pytest
   ./scripts/slopcheck.sh
   ```
5. Commit, then tag and push:

   ```bash
   git tag -a v0.1.1 -m "v0.1.1"
   git push origin main --follow-tags
   ```

The tag triggers `.github/workflows/release.yml`, which builds, runs `twine check`, installs the
wheel into a clean virtualenv to confirm the shipped example and `py.typed` actually made it, and
only then publishes.

## What the release workflow will not catch

`twine check` validates that the README renders as a PyPI long description. It does not check that
images resolve. **README image URLs must be absolute** `raw.githubusercontent.com` links: relative
paths work on GitHub and render broken on the PyPI project page.

## After the first publish

Add the PyPI and Python-version badges to the README. They sit in an HTML comment marked
`DEFER: add at the first PyPI release` and render broken until the project exists.

## Streamlit Community Cloud

The lab can be deployed from <https://share.streamlit.io>:

- Repository `jman4162/capex-atlas`, branch `main`, main file path `streamlit_app.py`.
- Cloud reads the root `requirements.txt`, which installs `-e .[app]`. It ignores pyproject extras,
  which is why that file exists.
- Cloud cannot pass command-line arguments, so the deployed app opens the example bundle shipped in
  the package. `capex-atlas app --bundle <path>` is the way to open a different one locally.

**Reboot the app after any commit that changes `src/`.** On a push Cloud logs `🔄 Updated app!` and
hot-swaps the page code without restarting the Python process, so modules already in `sys.modules`
stay at the build they were imported from and `@st.cache_resource` keeps objects of the old classes.
A commit that changes a page and the service layer together therefore deploys a page calling a
library that predates it, and the app dies on an `ImportError` or an `AttributeError` at startup.
Manage app → ⋮ → Reboot app forces a clean install and a fresh interpreter.

Two things reduce the blast radius but do not remove it: `requirements.txt` is editable, so a
rebuild always picks up the checkout, and `streamlit_app.py` puts `src/` ahead of site-packages, so
a fresh process cannot import a stale copy. Neither helps a process that is already running.

Once it is live, add the Streamlit badge to the README next to the others.
