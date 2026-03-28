import sys
import streamlit as st
import os
import yaml
import subprocess
import shutil
import re
from git import Repo

# --- 1. Détection des Chemins (Mode Sidecar) ---
# Emplacement physique du script (sovereign-spec-ai/)
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
# On regarde si le parent contient un .git
if os.path.exists(os.path.join(DASHBOARD_DIR, "..", ".git")):
    PROJECT_ROOT = os.path.abspath(os.path.join(DASHBOARD_DIR, ".."))
else:
    PROJECT_ROOT = DASHBOARD_DIR

# Chemins absolus dérivés
BASE_SPEC_PATH = os.path.join(PROJECT_ROOT, "specs")
ARCH_PATH = os.path.join(PROJECT_ROOT, "architecture")


# --- 2. Configuration & Persistence ---
def load_config():
    config_path = os.path.join(DASHBOARD_DIR, "factory_config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    return {
        "project_name": "SovereignSpec",
        "brand_emoji": "🤖",
        "stages": ["01_icebox", "02_backlog", "03_dev", "04_review", "05_done"],
        "default_model": "ollama/qwen2.5-coder:14b"
    }


config = load_config()
STAGES = config["stages"]


# --- 3. Fonctions de Logique ---

def get_repo():
    try:
        return Repo(PROJECT_ROOT)
    except:
        return None


def init_env():
    for stage in STAGES:
        os.makedirs(os.path.join(BASE_SPEC_PATH, stage), exist_ok=True)
    os.makedirs(ARCH_PATH, exist_ok=True)

    # Blueprint par défaut
    blueprint_path = os.path.join(ARCH_PATH, "project_blueprint.md")
    if not os.path.exists(blueprint_path):
        with open(blueprint_path, "w") as f:
            f.write(
                "# Project Blueprint\n\n## 🛠 Technical Stack\n- SvelteKit\n- Dexie.js\n\n## 📐 Domain Model\n```mermaid\ngraph TD\n    A --> B\n```")

    gitignore_path = os.path.join(PROJECT_ROOT, ".gitignore")
    tool_dir = os.path.basename(DASHBOARD_DIR)
    entry = f"\n# SovereignSpec Tooling\n{tool_dir}/\n"
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as f:
            content = f.read()
        if f"{tool_dir}/" not in content:
            with open(gitignore_path, "a") as f: f.write(entry)
    else:
        with open(gitignore_path, "w") as f:
            f.write(entry)
    st.rerun()

    # 3. Protection Aider (Création du .aiderignore à la racine)
    aiderignore_path = os.path.join(PROJECT_ROOT, ".aiderignore")
    tool_dir = os.path.basename(DASHBOARD_DIR)

    if not os.path.exists(aiderignore_path):
        with open(aiderignore_path, "w") as f:
            f.write(f"/{tool_dir}/\n")
            f.write("architecture*/\n")  # Optionnel: pour qu'il ne modifie pas le blueprint

def slugify(text):
    text = text.lower().replace('.md', '').strip()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[-\s]+', '_', text)


def move_spec(filename, from_stage, to_stage):
    source = os.path.join(BASE_SPEC_PATH, from_stage, filename)
    dest_dir = os.path.join(BASE_SPEC_PATH, to_stage)
    os.makedirs(dest_dir, exist_ok=True)
    if os.path.exists(source):
        shutil.move(source, os.path.join(dest_dir, filename))
        st.toast(f"✅ {filename} moved")


def run_agent(command, env_updates=None):
    custom_env = os.environ.copy()

    # 🔴 LE SECRET EST ICI: On force Python et Aider à cracher les logs en temps réel
    custom_env["PYTHONUNBUFFERED"] = "1"
    custom_env["AIDER_NO_COLORS"] = "1"  # Évite les bugs d'affichage liés au terminal

    if env_updates:
        custom_env.update(env_updates)

    terminal_output = st.empty()
    # On affiche la commande pour être sûr
    full_log = f"🚀 Démarrage de Frank...\n> {' '.join(command)}\n\n"
    terminal_output.code(full_log)

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=custom_env,
            cwd=PROJECT_ROOT  # On s'assure qu'Aider tourne dans le projet, pas dans l'outil
        )

        for line in process.stdout:
            full_log += line
            terminal_output.code(full_log)

        process.wait()
        return process.returncode

    except Exception as e:
        full_log += f"\n❌ ERREUR FATALE PYTHON: {e}"
        terminal_output.code(full_log)
        return 1


def run_agent_with_role(task_content, agent_file):
    agent_path = os.path.join(DASHBOARD_DIR, "agents", agent_file)
    if not os.path.exists(agent_path):
        st.error(f"Agent file {agent_file} not found!")
        return 1

    with open(agent_path, "r") as f:
        role_prompt = f.read()

    full_command = [
        sys.executable, "-m", "aider",
        "--model", config['default_model'],
        "--message", f"SYSTEM ROLE:\n{role_prompt}\n\nTASK:\n{task_content}",
        "--yes",
        "--no-auto-commits"
    ]

    # 🔴 N'OUBLIE PAS LE 'return' ICI :
    return run_agent(full_command, env_updates={"OLLAMA_API_BASE": "http://localhost:11434"})


def trigger_dev_swarm(task_filename):
    repo = get_repo()
    branch = slugify(task_filename)
    try:
        repo.git.checkout('main')
        repo.git.checkout('-b', branch)
    except:
        repo.git.checkout(branch)

    move_spec(task_filename, "02_backlog", "03_dev")

    with open(os.path.join(BASE_SPEC_PATH, "03_dev", task_filename), "r") as f:
        content = f.read()

    # On capture le code de retour
    result = run_agent_with_role(content, "developer.md")

    if result == 0:
        move_spec(task_filename, "03_dev", "04_review")
        return True
    else:
        st.error(f"❌ L'agent a échoué (Code {result}). Le processus est en pause pour te laisser lire le log.")
        return False


# --- 4. UI Setup ---
st.set_page_config(layout="wide", page_title=config['project_name'], page_icon=config['brand_emoji'])
st.title(f"{config['brand_emoji']} {config['project_name']}")
repo = get_repo()

with st.sidebar:
    st.header("⚙️ Admin")
    if not os.path.exists(BASE_SPEC_PATH):
        if st.button("🚀 Initialize Environment"): init_env()
    else:
        if repo:
            try:
                st.caption(f"📍 Branch: `{repo.active_branch.name}`")
            except:
                st.caption("📍 Git Ready")

    st.divider()
    if os.path.exists(ARCH_PATH):
        st.subheader("📐 Architecture & Blueprint")
        bp_files = [f for f in os.listdir(ARCH_PATH) if f.endswith(".md")]
        selected_bp = st.selectbox("Select Blueprint", bp_files)
        if selected_bp:
            with open(os.path.join(ARCH_PATH, selected_bp), "r") as f:
                bp_content = f.read()
            st.markdown(bp_content)
            if st.button("🏗️ Generate Backlog"):
                st.info("Architect is analyzing the Blueprint...")
                icebox_path = os.path.abspath(os.path.join(BASE_SPEC_PATH, "01_icebox"))

                prompt = f"""
                            Decompose this Blueprint into atomic tasks.
                            Create files in: {icebox_path}

                            BLUEPRINT:
                            {bp_content}
                            """
                result = run_agent_with_role(prompt, "architect.md")

                if result == 0:
                    st.success("✅ Icebox populated! Refreshing...")
                    st.rerun()  # On rafraîchit SEULEMENT si c'est un succès
                else:
                    st.error(f"❌ Erreur (Code {result}). Lis le log noir ci-dessus.")

    st.divider()
    agent_dir = os.path.join(DASHBOARD_DIR, "agents")
    agent_list = os.listdir(agent_dir) if os.path.exists(agent_dir) else ["developer.md"]
    selected_agent = st.selectbox("🎭 Agent Role", agent_list)

    # --- 5. Edit Modal ---
    if "editing" in st.session_state:
        file_path = st.session_state.editing
        st.divider()
        st.subheader(f"✏️ Edit: {os.path.basename(file_path)}")

        try:
            with open(file_path, "r") as f:
                content = f.read()

            new_content = st.text_area("Markdown Content", value=content, height=400)

            c1, c2, c3 = st.columns([1, 1, 4])
            with c1:
                if st.button("💾 Save Changes"):
                    with open(file_path, "w") as f:
                        f.write(new_content)
                    del st.session_state.editing
                    st.rerun()
            with c2:
                if st.button("❌ Cancel"):
                    del st.session_state.editing
                    st.rerun()
        except Exception as e:
            st.error(f"Error reading file: {e}")
            if st.button("Close"):
                del st.session_state.editing
                st.rerun()


# --- 6. Review Modal ---
if "review_target" in st.session_state:
    target = st.session_state.review_target
    branch = slugify(target)
    st.divider()
    st.subheader(f"🧐 Review: {target}")
    if st.button("🤖 Ask Agent Reviewer"):
        with open("agents/reviewer.md", "r") as f: role_prompt = f.read()
        clean_diff = repo.git.diff("main", branch, "--", ".", ":!specs/", ":!architecture/")
        cmd = ["aider", "--model", config['default_model'], "--message", f"ROLE:\n{role_prompt}\n\nDIFF:\n{clean_diff}",
               "--read", os.path.join(BASE_SPEC_PATH, "04_review", target), "--yes"]
        run_agent(cmd, env_updates={"OLLAMA_API_BASE": "http://localhost:11434"})

    try:
        clean_diff_display = repo.git.diff("main", branch, "--", ".", ":!specs/", ":!architecture/")
        st.code(clean_diff_display, language="diff")
    except:
        st.warning("Diff indisponible")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("✅ Approve"):
            repo.git.checkout('main');
            repo.git.merge(branch);
            repo.git.branch('-d', branch)
            move_spec(target, "04_review", "05_done")
            del st.session_state.review_target
            st.rerun()
    with c2:
        reason = st.text_input("Feedback")
        if st.button("❌ Reject"):
            move_spec(target, "04_review", "02_backlog");
            append_feedback_to_spec(target, reason)
            del st.session_state.review_target
            st.rerun()
    with c3:
        if st.button("Cancel"):
            del st.session_state.review_target
            st.rerun()

# --- 5. Kanban ---
if os.path.exists(BASE_SPEC_PATH):
    cols = st.columns(len(STAGES))
    for i, stage in enumerate(STAGES):
        with cols[i]:
            st.markdown(f"### {stage.split('_')[1].upper()}")
            path = os.path.join(BASE_SPEC_PATH, stage)

            if os.path.exists(path):
                files = sorted([f for f in os.listdir(path) if f.endswith(".md")])
                if not files:
                    st.caption("Empty")
                for file in files:
                    with st.expander(f"📄 {file}"):
                        if stage == "02_backlog" and st.button("▶️ Start", key=f"run_{file}"):
                            success = trigger_dev_swarm(file)
                            if success:
                                st.rerun()  # On rafraîchit UNIQUEMENT si Frank a réussi
                        if stage == "04_review" and st.button("🔍 Review", key=f"rev_{file}"):
                            st.session_state.review_target = file
                        if st.button("👁️ Edit", key=f"ed_{file}"):
                            st.session_state.editing = os.path.join(path, file)
            else:
                st.error("Folder missing")
else:
    st.error(f"FATAL: BASE_SPEC_PATH non trouvé à : {BASE_SPEC_PATH}")
    st.info(f"PROJECT_ROOT actuel : {PROJECT_ROOT}")
