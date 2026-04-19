// Pokédex front-end — localized.
//
// Three-tier loading:
//   1. /api/languages + /api/games                     → shell population
//   2. /api/{lang}/strings                             → UI + type + trigger labels
//   3. /api/{lang}/games/{id}                          → summary list
//   4. /api/{lang}/games/{id}/{species_id}             → full entry (lazy)
// Strings, summaries and full entries are cached per language.

const els = {
    gameSelect: document.getElementById("game-select"),
    langSelect: document.getElementById("lang-select"),
    list: document.getElementById("pokemon-list"),
    detail: document.getElementById("detail"),
    search: document.getElementById("search"),
    count: document.getElementById("count"),
    template: document.getElementById("entry-template"),
};

const LANG_KEY = "pokedex-lang";
const DEFAULT_LANG = "en";

const state = {
    lang: localStorage.getItem(LANG_KEY) || DEFAULT_LANG,
    languages: [],
    strings: null,
    games: [],
    currentGame: null,
    summary: null,
    entryCache: new Map(),      // key: "<lang>:<game>:<species_id>" → PokedexEntry
    selectedSpeciesId: null,
    searchTerm: "",
    detailReqId: 0,
};

init().catch((err) => {
    console.error(err);
    els.detail.innerHTML = `<p class="empty-state">${err.message}</p>`;
});

async function init() {
    const [languages, idx] = await Promise.all([
        fetchJSON("/api/languages").then((r) => r.languages),
        fetchJSON("/api/games").then((r) => r.games),
    ]);
    state.languages = languages;
    state.games = idx;
    if (!languages.some((l) => l.code === state.lang)) state.lang = DEFAULT_LANG;
    await loadStrings();

    populateLanguages(languages);
    populateGames(idx);
    applyStaticI18n();

    const initial = parseHashGame() || idx[0].id;
    els.gameSelect.value = initial;
    await loadGame(initial);

    els.langSelect.addEventListener("change", async (e) => {
        state.lang = e.target.value;
        localStorage.setItem(LANG_KEY, state.lang);
        document.documentElement.lang = state.lang;
        await loadStrings();
        populateGames(state.games);   // refresh the "Generation X" labels
        els.gameSelect.value = state.currentGame;
        applyStaticI18n();
        const keepId = state.selectedSpeciesId;
        state.summary = null;
        await loadGame(state.currentGame, keepId);
    });

    els.gameSelect.addEventListener("change", async (e) => {
        await loadGame(e.target.value);
        history.replaceState(null, "", `#${e.target.value}`);
    });

    els.search.addEventListener("input", (e) => {
        state.searchTerm = e.target.value.trim().toLowerCase();
        renderList();
    });

    window.addEventListener("hashchange", () => {
        const g = parseHashGame();
        if (g && g !== state.currentGame) {
            els.gameSelect.value = g;
            loadGame(g);
        }
    });
}

function parseHashGame() {
    const h = window.location.hash.slice(1);
    return state.games.some((g) => g.id === h) ? h : null;
}

async function fetchJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status} from ${url}`);
    return r.json();
}

async function loadStrings() {
    state.strings = await fetchJSON(`/api/${state.lang}/strings`);
    document.documentElement.lang = state.lang;
}

function t(key, params = {}) {
    let s = (state.strings?.ui && state.strings.ui[key]) || key;
    for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, v);
    return s;
}

function typeLabel(key) {
    return (state.strings?.types && state.strings.types[key])
        || (key[0].toUpperCase() + key.slice(1));
}

function damageClassLabel(key) {
    return (state.strings?.damage_class && state.strings.damage_class[key])
        || (key[0].toUpperCase() + key.slice(1));
}

function triggerLabel(key) {
    return (state.strings?.triggers && state.strings.triggers[key]) || key;
}

function populateLanguages(languages) {
    els.langSelect.innerHTML = "";
    for (const l of languages) {
        const o = document.createElement("option");
        o.value = l.code;
        o.textContent = l.native_name;
        els.langSelect.appendChild(o);
    }
    els.langSelect.value = state.lang;
}

function populateGames(games) {
    const grouped = {};
    for (const g of games) (grouped[g.generation] ||= []).push(g);
    els.gameSelect.innerHTML = "";
    Object.keys(grouped)
        .sort((a, b) => Number(a) - Number(b))
        .forEach((gen) => {
            const og = document.createElement("optgroup");
            og.label = `${t("generation")} ${roman(Number(gen))}`;
            for (const game of grouped[gen]) {
                const o = document.createElement("option");
                o.value = game.id;
                o.textContent = `${game.name} (${game.release_year})`;
                og.appendChild(o);
            }
            els.gameSelect.appendChild(og);
        });
}

function applyStaticI18n() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
        el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
        el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
        el.setAttribute("aria-label", t(el.dataset.i18nAria));
    });
    document.title = `${t("title")} · PÓkE-GooGle`;
}

function roman(n) {
    return ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"][n] || n;
}

async function loadGame(gameId, restoreSpeciesId = null) {
    state.currentGame = gameId;
    state.selectedSpeciesId = restoreSpeciesId;
    els.list.innerHTML = `<li class="loading">${t("loading")}</li>`;
    els.detail.className = "detail empty";
    els.detail.innerHTML = `<p class="empty-state">${t("loading")}</p>`;
    els.count.textContent = "";

    state.summary = await fetchJSON(
        `/api/${state.lang}/games/${encodeURIComponent(gameId)}`,
    );

    renderList();
    const defaultId = restoreSpeciesId
        && state.summary.pokemon.some((p) => p.species_id === restoreSpeciesId)
            ? restoreSpeciesId
            : (state.summary.pokemon[0]?.species_id ?? null);
    if (defaultId != null) {
        selectPokemon(defaultId);
    } else {
        els.detail.innerHTML = `<p class="empty-state">${t("no_pokemon_in_game")}</p>`;
    }
}

function renderList() {
    const term = state.searchTerm;
    const items = state.summary.pokemon.filter((p) => {
        if (!term) return true;
        const num = String(p.regional_number ?? p.national_number);
        return p.name.toLowerCase().includes(term) || num.includes(term);
    });

    els.count.textContent = `${items.length}/${state.summary.pokemon.length}`;

    const frag = document.createDocumentFragment();
    for (const p of items) {
        const li = document.createElement("li");
        li.dataset.species = p.species_id;
        if (p.species_id === state.selectedSpeciesId) li.classList.add("selected");

        const img = document.createElement("img");
        img.className = "thumb";
        img.loading = "lazy";
        img.alt = p.name;
        img.src = p.sprite_url;
        li.appendChild(img);

        const meta = document.createElement("div");
        meta.innerHTML = `
            <div class="num">#${String(p.national_number).padStart(4, "0")}${p.regional_number ? ` · loc ${p.regional_number}` : ""}</div>
            <div class="name">${escapeHtml(p.name)}</div>
            <div class="types">${p.types.map(typePill).join("")}</div>
        `;
        li.appendChild(meta);
        li.addEventListener("click", () => selectPokemon(p.species_id));
        frag.appendChild(li);
    }
    els.list.replaceChildren(frag);
}

async function selectPokemon(speciesId) {
    state.selectedSpeciesId = speciesId;
    [...els.list.querySelectorAll("li")].forEach((li) =>
        li.classList.toggle("selected", Number(li.dataset.species) === speciesId),
    );

    const cacheKey = `${state.lang}:${state.currentGame}:${speciesId}`;
    const reqId = ++state.detailReqId;

    let entry = state.entryCache.get(cacheKey);
    if (!entry) {
        els.detail.className = "detail empty";
        els.detail.innerHTML = `<p class="empty-state">${t("loading")}</p>`;
        try {
            entry = await fetchJSON(
                `/api/${state.lang}/games/${encodeURIComponent(state.currentGame)}/${speciesId}`,
            );
            state.entryCache.set(cacheKey, entry);
        } catch (err) {
            if (reqId !== state.detailReqId) return;
            els.detail.innerHTML = `<p class="empty-state">${t("failed_entry", { msg: err.message })}</p>`;
            return;
        }
    }
    if (reqId !== state.detailReqId || state.selectedSpeciesId !== speciesId) return;
    renderDetail(entry);
}

function renderDetail(p) {
    const tpl = els.template.content.cloneNode(true);
    const root = tpl.querySelector(".entry");

    const art = root.querySelector(".entry-art");
    art.src = p.sprite_url;
    art.alt = p.name;
    if (state.summary.game.sprite_kind === "official-artwork") art.classList.add("high-res");
    art.onerror = () => { art.src = p.artwork_url; art.classList.add("high-res"); };

    root.querySelector(".entry-id").textContent =
        `#${String(p.national_number).padStart(4, "0")} · ${t("national_pokedex")}`;
    root.querySelector(".entry-name").textContent = p.name;
    root.querySelector(".entry-genus").textContent = p.genus || "";

    root.querySelector(".entry-types").innerHTML = p.types.map(typePill).join("");
    root.querySelector(".height").textContent = `${p.height_m.toFixed(1)} m`;
    root.querySelector(".weight").textContent = `${p.weight_kg.toFixed(1)} kg`;
    root.querySelector(".stage").textContent = `${p.evolution.stage}`;
    root.querySelector(".regional").textContent = p.regional_number ?? "—";

    root.querySelector(".entry-description").textContent =
        p.description || t("no_description");

    const weakUl = root.querySelector(".entry-weaknesses");
    if (p.weaknesses.length === 0) {
        weakUl.innerHTML = `<li>${t("no_weaknesses")}</li>`;
    } else {
        for (const w of p.weaknesses) {
            const li = document.createElement("li");
            li.innerHTML = `${typePill(w.type)} <span class="multiplier">×${w.multiplier}</span>`;
            weakUl.appendChild(li);
        }
    }

    renderEvolution(root.querySelector(".entry-evolution"), p);

    const movesBody = root.querySelector(".moves-body");
    const chipsEl = root.querySelector(".moves-type-chips");
    const countEl = root.querySelector(".moves-count");
    let activeType = "all";
    const draw = () => {
        chipsEl.querySelectorAll(".moves-type-chip").forEach((c) => {
            c.classList.toggle("active", c.dataset.type === activeType);
            c.setAttribute("aria-pressed", c.dataset.type === activeType ? "true" : "false");
        });
        const subset = activeType === "all"
            ? p.moves
            : p.moves.filter((m) => m.type === activeType);
        countEl.textContent = `${subset.length}/${p.moves.length}`;
        renderMoves(movesBody, subset);
    };
    renderMoveTypeChips(chipsEl, p.moves, (type) => {
        activeType = type;
        draw();
    });
    draw();

    els.detail.className = "detail";
    els.detail.replaceChildren(root);
    els.detail.scrollTop = 0;
}

function renderEvolution(container, p) {
    container.innerHTML = "";
    const evo = p.evolution;
    const nameToSpeciesId = new Map(
        state.summary.pokemon.map((s) => [s.name, s.species_id]),
    );

    if (evo.evolves_from) {
        container.appendChild(node(evo.evolves_from));
        container.appendChild(arrow("→"));
    }
    container.appendChild(node(p.name, true));
    if (evo.evolves_to.length > 0) {
        container.appendChild(arrow("→"));
        evo.evolves_to.forEach((tgt, i) => {
            if (i > 0) container.appendChild(arrow("·"));
            container.appendChild(node(tgt.species));
            const trig = document.createElement("span");
            trig.className = "evo-trigger";
            trig.textContent = evoLabel(tgt);
            container.appendChild(trig);
        });
    } else if (!evo.evolves_from) {
        const note = document.createElement("span");
        note.className = "evo-trigger";
        note.textContent = t("does_not_evolve");
        container.appendChild(note);
    }

    const stage = document.createElement("span");
    stage.className = "stage-badge";
    stage.textContent = t("stage_badge", { stage: evo.stage });
    container.appendChild(stage);

    function node(name, current = false) {
        const span = document.createElement("span");
        span.className = "evo-node" + (current ? " current" : "");
        span.textContent = name;

        const targetId = nameToSpeciesId.get(name);
        if (targetId == null) {
            span.classList.add("unavailable");
            span.title = t("not_in_game", { name, game: state.summary.game.name });
        } else if (!current) {
            span.classList.add("clickable");
            span.setAttribute("role", "button");
            span.setAttribute("tabindex", "0");
            span.title = t("open_pokemon", { name });
            const go = (ev) => {
                ev.preventDefault();
                selectPokemon(targetId);
            };
            span.addEventListener("click", go);
            span.addEventListener("keydown", (ev) => {
                if (ev.key === "Enter" || ev.key === " ") go(ev);
            });
        }
        return span;
    }
    function arrow(c) {
        const s = document.createElement("span");
        s.className = "evo-arrow";
        s.textContent = c;
        return s;
    }
}

function evoLabel(target) {
    const label = triggerLabel(target.trigger);
    if (target.min_level) return `${label} ${target.min_level}`;
    return label;
}

function renderMoveTypeChips(container, moves, onPick) {
    const types = [...new Set(moves.map((m) => m.type))].sort();
    container.innerHTML = "";

    const makeChip = (type, label, count) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.dataset.type = type;
        chip.className = type === "all"
            ? "moves-type-chip chip-all"
            : `moves-type-chip type-${type}`;
        chip.setAttribute("aria-pressed", "false");
        chip.innerHTML = `<span class="chip-label">${escapeHtml(label)}</span><span class="chip-count">${count}</span>`;
        chip.addEventListener("click", () => onPick(type));
        return chip;
    };

    container.appendChild(makeChip("all", t("all_types"), moves.length));
    for (const type of types) {
        const count = moves.reduce((acc, m) => acc + (m.type === type ? 1 : 0), 0);
        container.appendChild(makeChip(type, typeLabel(type), count));
    }
}

function renderMoves(tbody, moves) {
    tbody.innerHTML = "";
    if (moves.length === 0) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td colspan="8" style="text-align:center; opacity:.6">${t("no_moves")}</td>`;
        tbody.appendChild(tr);
        return;
    }
    for (const m of moves) {
        const tr = document.createElement("tr");
        const lvl = m.level_learned != null
            ? m.level_learned
            : (m.learn_method === "level-up" ? "—" : m.learn_method[0].toUpperCase());
        tr.innerHTML = `
            <td data-label="${escapeHtml(t("col_lv"))}">${lvl}</td>
            <td class="move-name" data-label="${escapeHtml(t("col_move"))}">${escapeHtml(m.name)}</td>
            <td data-label="${escapeHtml(t("col_type"))}">${typePill(m.type)}</td>
            <td class="damage-${m.damage_class}" data-label="${escapeHtml(t("col_class"))}">${escapeHtml(damageClassLabel(m.damage_class))}</td>
            <td data-label="${escapeHtml(t("col_pwr"))}">${m.power ?? "—"}</td>
            <td data-label="${escapeHtml(t("col_acc"))}">${m.accuracy != null ? m.accuracy + "%" : "—"}</td>
            <td data-label="${escapeHtml(t("col_pp"))}">${m.pp ?? "—"}</td>
            <td class="desc" data-label="${escapeHtml(t("col_description"))}">${escapeHtml(m.description || "")}</td>
        `;
        tbody.appendChild(tr);
    }
}

function typePill(typeKey) {
    const key = String(typeKey).toLowerCase();
    return `<span class="type-pill type-${key}">${escapeHtml(typeLabel(key))}</span>`;
}

function escapeHtml(s) {
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
