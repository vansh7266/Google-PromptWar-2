/**
 * VoteIndiaSmart — Main JavaScript
 * Handles chat, quiz, animations, timeline learn-more,
 * process cards, counter animation, and navbar.
 */

"use strict";

/* Google Translate initialisation (must be global for callback) */
window.googleTranslateElementInit = function () {
    new google.translate.TranslateElement(
        {
            pageLanguage: "en",
            includedLanguages: "hi,en,ta,te,bn,mr,gu,kn,ml,pa",
            layout: google.translate.TranslateElement.InlineLayout.SIMPLE,
        },
        "google_translate_element"
    );
};

/* Utilities */

/**
 * Escape special HTML characters to prevent XSS.
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return String(str).replace(/[&<>"']/g, (ch) => map[ch]);
}

/**
 * Convert newlines to HTML paragraph/break tags.
 * @param {string} text
 * @returns {string}
 */
function nl2br(text) {
    return escapeHtml(text).replace(/\n{2,}/g, "</p><p>").replace(/\n/g, "<br>");
}

/**
 * Wrap plain text in paragraph tags for bot message display.
 * @param {string} text
 * @returns {string}
 */
function formatBotMessage(text) {
    return `<p>${nl2br(text)}</p>`;
}

/* Reveal animations */
(function initReveal() {
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add("visible");
                    observer.unobserve(entry.target);
                }
            });
        },
        { threshold: 0.12 }
    );
    document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));
})();

/* Counter animation (hero stats) */
(function initCounters() {
    const counters = document.querySelectorAll(".stat-card__number[data-target]");
    if (!counters.length) return;

    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                const el = entry.target;
                const target = parseInt(el.dataset.target, 10);
                const duration = 1600;
                const start = performance.now();

                function step(now) {
                    const elapsed = now - start;
                    const progress = Math.min(elapsed / duration, 1);
                    const eased = 1 - Math.pow(1 - progress, 3);
                    el.textContent = Math.floor(eased * target);
                    if (progress < 1) requestAnimationFrame(step);
                    else el.textContent = target;
                }

                requestAnimationFrame(step);
                observer.unobserve(el);
            });
        },
        { threshold: 0.5 }
    );
    counters.forEach((el) => observer.observe(el));
})();

/* Navbar — scroll shadow + mobile menu */
(function initNavbar() {
    const header = document.getElementById("header");
    const hamburger = document.getElementById("navHamburger");
    const mobileMenu = document.getElementById("navMobile");
    const navLinks = document.querySelectorAll(".nav__link");

    window.addEventListener("scroll", () => {
        header.classList.toggle("scrolled", window.scrollY > 10);
    }, { passive: true });

    hamburger.addEventListener("click", () => {
        const isOpen = mobileMenu.classList.toggle("open");
        hamburger.classList.toggle("open", isOpen);
        hamburger.setAttribute("aria-expanded", String(isOpen));
        mobileMenu.setAttribute("aria-hidden", String(!isOpen));
    });

    const sections = document.querySelectorAll("section[id]");

    function updateActiveLink() {
        let current = "";
        sections.forEach((section) => {
            const top = section.offsetTop - 90;
            if (window.scrollY >= top) current = section.id;
        });
        navLinks.forEach((link) => {
            const href = link.getAttribute("href")?.replace("#", "");
            link.classList.toggle("active", href === current);
        });
    }

    window.addEventListener("scroll", updateActiveLink, { passive: true });

    document.querySelectorAll(".nav__mobile .nav__link").forEach((link) => {
        link.addEventListener("click", () => {
            mobileMenu.classList.remove("open");
            hamburger.classList.remove("open");
            hamburger.setAttribute("aria-expanded", "false");
            mobileMenu.setAttribute("aria-hidden", "true");
        });
    });
})();

/* Modal — for timeline & process card explanations */
const Modal = (function () {
    const overlay = document.getElementById("modalOverlay");
    const modalEl = overlay.querySelector(".modal");
    const titleEl = document.getElementById("modalTitle");
    const loadingEl = document.getElementById("modalLoading");
    const contentEl = document.getElementById("modalContent");
    const closeBtn = document.getElementById("modalClose");

    /** @type {HTMLElement|null} */
    let previousFocus = null;

    /**
     * Trap keyboard focus inside the modal.
     * @param {KeyboardEvent} e
     */
    function trapFocus(e) {
        if (e.key !== "Tab") return;
        const focusable = modalEl.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    }

    function open(title) {
        previousFocus = document.activeElement;
        titleEl.textContent = title;
        loadingEl.hidden = false;
        contentEl.hidden = true;
        contentEl.innerHTML = "";
        overlay.hidden = false;
        document.body.style.overflow = "hidden";
        closeBtn.focus();
        modalEl.addEventListener("keydown", trapFocus);
    }

    function setContent(text) {
        contentEl.innerHTML = formatBotMessage(text);
        loadingEl.hidden = true;
        contentEl.hidden = false;
    }

    function setError(msg) {
        contentEl.innerHTML = `<p class="modal__error">⚠️ ${escapeHtml(msg)}</p>`;
        loadingEl.hidden = true;
        contentEl.hidden = false;
    }

    function close() {
        overlay.hidden = true;
        document.body.style.overflow = "";
        modalEl.removeEventListener("keydown", trapFocus);
        if (previousFocus) previousFocus.focus();
    }

    closeBtn.addEventListener("click", close);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });

    return { open, setContent, setError };
})();

/* AI explanation — shared fetch for modal */
async function fetchAIExplanation(topic) {
    Modal.open(topic);

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: `Explain in detail: ${topic}`, history: [] }),
        });

        if (!response.ok) {
            throw new Error(`Server responded with status ${response.status}`);
        }

        const data = await response.json();

        if (data.status === "success" && data.reply) {
            Modal.setContent(data.reply);
        } else {
            Modal.setError(data.error || "Could not fetch explanation. Please try again.");
        }
    } catch (err) {
        console.error("AI explanation error:", err);
        Modal.setError("Network error. Please check your connection and try again.");
    }
}

/* Timeline — "Learn More" buttons */
(function initTimeline() {
    document.querySelectorAll(".timeline__learn-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const topic = btn.dataset.topic;
            if (topic) fetchAIExplanation(topic);
        });
    });
})();

/* Process cards */
(function initProcessCards() {
    document.querySelectorAll(".process-card").forEach((card) => {
        card.addEventListener("click", () => {
            const topic = card.dataset.topic;
            if (topic) fetchAIExplanation(topic);
        });

        card.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                card.click();
            }
        });
        card.setAttribute("tabindex", "0");
        card.setAttribute("role", "button");
    });
})();

/* Quiz */
(function initQuiz() {
    const newQuestionBtn = document.getElementById("newQuestionBtn");
    const btnText = document.getElementById("newQuestionBtnText");
    const spinner = document.getElementById("quizSpinner");
    const placeholder = document.getElementById("quizPlaceholder");
    const questionWrap = document.getElementById("quizQuestionWrap");
    const questionText = document.getElementById("quizQuestion");
    const optionsContainer = document.getElementById("quizOptions");
    const resultDiv = document.getElementById("quizResult");
    const resultIcon = document.getElementById("quizResultIcon");
    const resultText = document.getElementById("quizResultText");
    const explanationEl = document.getElementById("quizExplanation");
    const scoreEl = document.getElementById("quizScore");
    const totalEl = document.getElementById("quizTotal");
    const difficultyBtns = document.querySelectorAll(".difficulty-btn");

    let difficulty = "medium";
    let score = 0;
    let total = 0;
    let isLoading = false;

    difficultyBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
            difficultyBtns.forEach((b) => {
                b.classList.remove("active");
                b.setAttribute("aria-pressed", "false");
            });
            btn.classList.add("active");
            btn.setAttribute("aria-pressed", "true");
            difficulty = btn.dataset.level;
        });
    });

    newQuestionBtn.addEventListener("click", fetchQuestion);

    async function fetchQuestion() {
        if (isLoading) return;
        isLoading = true;

        btnText.hidden = true;
        spinner.hidden = false;
        newQuestionBtn.disabled = true;
        placeholder.hidden = true;
        questionWrap.hidden = true;
        resultDiv.hidden = true;
        optionsContainer.innerHTML = "";

        try {
            const response = await fetch("/api/quiz", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ difficulty }),
            });

            if (!response.ok) throw new Error(`Server error: ${response.status}`);
            const data = await response.json();
            if (data.status !== "success") {
                throw new Error(data.error || "Failed to generate question.");
            }
            renderQuestion(data);
        } catch (err) {
            console.error("Quiz error:", err);
            placeholder.hidden = false;
            placeholder.querySelector("p").textContent =
                "⚠️ Could not load question. Please try again.";
        } finally {
            isLoading = false;
            btnText.hidden = false;
            spinner.hidden = true;
            newQuestionBtn.disabled = false;
        }
    }

    function renderQuestion({ question, options, correct_index, explanation }) {
        questionText.textContent = question;

        const letters = ["A", "B", "C", "D"];
        options.forEach((option, idx) => {
            const btn = document.createElement("button");
            btn.className = "quiz__option";
            btn.setAttribute("role", "radio");
            btn.setAttribute("aria-checked", "false");
            btn.setAttribute("aria-label", `Option ${letters[idx]}: ${option}`);
            btn.innerHTML = `
                <span class="quiz__option-letter">${escapeHtml(letters[idx])}</span>
                <span>${escapeHtml(option)}</span>
            `;
            btn.addEventListener("click", () => handleAnswer(idx, options, correct_index, explanation));
            optionsContainer.appendChild(btn);
        });

        questionWrap.hidden = false;
        resultDiv.hidden = true;
    }

    function handleAnswer(selectedIdx, options, correctIdx, explanation) {
        total++;
        totalEl.textContent = total;

        const allBtns = optionsContainer.querySelectorAll(".quiz__option");
        allBtns.forEach((btn) => {
            btn.disabled = true;
            btn.setAttribute("aria-checked", "false");
        });

        allBtns[correctIdx].classList.add("correct");
        allBtns[correctIdx].setAttribute("aria-checked", "true");

        if (selectedIdx !== correctIdx) {
            allBtns[selectedIdx].classList.add("wrong");
            resultIcon.textContent = "❌";
            resultText.textContent = `Incorrect! The correct answer was: "${options[correctIdx]}"`;
        } else {
            score++;
            scoreEl.textContent = score;
            resultIcon.textContent = "✅";
            resultText.textContent = "Correct! Well done!";
        }

        explanationEl.textContent = explanation;
        resultDiv.hidden = false;
    }
})();

/* Chat */
(function initChat() {
    const chatWindow = document.getElementById("chatWindow");
    const chatInput = document.getElementById("chatInput");
    const sendBtn = document.getElementById("chatSendBtn");
    const charCount = document.getElementById("charCount");
    const suggestions = document.getElementById("chatSuggestions");
    const chips = document.querySelectorAll(".chip");

    const conversationHistory = [];

    chatInput.addEventListener("input", () => {
        chatInput.style.height = "auto";
        chatInput.style.height = `${Math.min(chatInput.scrollHeight, 140)}px`;
        const len = chatInput.value.length;
        charCount.textContent = `${len}/500`;
        sendBtn.disabled = len === 0;
    });

    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!sendBtn.disabled) sendMessage();
        }
    });

    sendBtn.addEventListener("click", sendMessage);

    chips.forEach((chip) => {
        chip.addEventListener("click", () => {
            const msg = chip.dataset.msg;
            if (msg) {
                chatInput.value = msg;
                chatInput.dispatchEvent(new Event("input"));
                sendMessage();
                suggestions.style.display = "none";
            }
        });
    });

    function sendMessage() {
        const rawText = chatInput.value.trim();
        if (!rawText) return;

        appendMessage("user", rawText);

        chatInput.value = "";
        chatInput.style.height = "auto";
        charCount.textContent = "0/500";
        sendBtn.disabled = true;

        const typingId = appendTyping();
        fetchBotReply(rawText, typingId);
    }

    function appendMessage(role, text) {
        const div = document.createElement("div");
        div.className = `chat__message chat__message--${role}`;

        const avatar = document.createElement("div");
        avatar.className = "chat__avatar";
        avatar.setAttribute("aria-hidden", "true");
        avatar.textContent = role === "bot" ? "🗳️" : "👤";

        const bubble = document.createElement("div");
        bubble.className = "chat__bubble";

        if (role === "bot") {
            bubble.innerHTML = formatBotMessage(text);
        } else {
            bubble.textContent = text;
        }

        div.appendChild(avatar);
        div.appendChild(bubble);
        chatWindow.appendChild(div);
        scrollToBottom();
    }

    function appendTyping() {
        const id = `typing-${Date.now()}`;
        const div = document.createElement("div");
        div.className = "chat__message chat__message--bot chat__typing";
        div.id = id;

        const avatar = document.createElement("div");
        avatar.className = "chat__avatar";
        avatar.setAttribute("aria-hidden", "true");
        avatar.textContent = "🗳️";

        const dots = document.createElement("div");
        dots.className = "chat__typing-dots";
        dots.setAttribute("aria-label", "AI is typing");
        dots.innerHTML = "<span></span><span></span><span></span>";

        div.appendChild(avatar);
        div.appendChild(dots);
        chatWindow.appendChild(div);
        scrollToBottom();
        return id;
    }

    function removeTyping(typingId) {
        document.getElementById(typingId)?.remove();
    }

    async function fetchBotReply(userMessage, typingId) {
        conversationHistory.push({ role: "user", content: userMessage });
        if (conversationHistory.length > 12) conversationHistory.splice(0, 2);

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: userMessage,
                    history: conversationHistory.slice(-6),
                }),
            });

            removeTyping(typingId);

            if (!response.ok) {
                throw new Error(`Server error ${response.status}`);
            }

            const data = await response.json();

            if (data.status === "success" && data.reply) {
                conversationHistory.push({ role: "assistant", content: data.reply });
                appendMessage("bot", data.reply);
            } else {
                appendMessage("bot", data.error || "Sorry, something went wrong. Please try again.");
            }
        } catch (err) {
            removeTyping(typingId);
            console.error("Chat fetch error:", err);
            appendMessage("bot", "⚠️ Network error. Please check your connection and try again.");
        }
    }

    function scrollToBottom() {
        chatWindow.scrollTo({ top: chatWindow.scrollHeight, behavior: "smooth" });
    }
})();

/* Smooth scroll for anchor links */
(function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
        anchor.addEventListener("click", (e) => {
            const target = document.querySelector(anchor.getAttribute("href"));
            if (target) {
                e.preventDefault();
                const offset = 80;
                const top = target.getBoundingClientRect().top + window.scrollY - offset;
                window.scrollTo({ top, behavior: "smooth" });
            }
        });
    });
})();

/* Floating chat FAB */
document.getElementById("chatFab")?.addEventListener("click", () => {
    document.getElementById("chat").scrollIntoView({ behavior: "smooth" });
    setTimeout(() => document.getElementById("chatInput").focus(), 600);
});