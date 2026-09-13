const state = { data: null };

const $ = (id) => document.getElementById(id);
const money = (n) => Number(n ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 });
const count = (n) => String(Math.max(0, Number(n ?? 0))).padStart(2, "0");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
}[c]));
const fmtDate = (s) => {
  if (!s) return "—";
  const d = new Date(`${s}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? esc(s)
    : d.toLocaleDateString("en-US", { year:"numeric", month:"short", day:"numeric" });
};
const normalize = (s) => String(s ?? "").trim().toUpperCase();
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

async function loadData(){
  const res = await fetch("data.json", { cache:"no-store" });
  if(!res.ok) throw new Error("Data source unavailable.");
  state.data = await res.json();
}

function animateNumber(target, value){
  if(!target) return;
  const finalValue = Number(value);
  if(!Number.isFinite(finalValue)){
    target.textContent = "—";
    return;
  }
  if(reducedMotion()){
    target.textContent = money(finalValue);
    return;
  }
  const duration = 520;
  const start = performance.now();
  const from = 0;
  const frame = (now) => {
    const progress = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    target.textContent = money(from + (finalValue - from) * eased);
    if(progress < 1) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

function animateCount(target, value){
  if(!target) return;
  const finalValue = Math.max(0, Math.floor(Number(value ?? 0)));
  if(reducedMotion()){
    target.textContent = String(finalValue).padStart(2, "0");
    return;
  }
  const duration = 420;
  const start = performance.now();
  const frame = (now) => {
    const progress = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(finalValue * eased);
    target.textContent = String(current).padStart(2, "0");
    if(progress < 1) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

function renderAwardList(targetId, awards, emptyText){
  const target = $(targetId);
  if(!target) return;

  if(!awards.length){
    target.innerHTML = `<div class="award-empty">${esc(emptyText)}</div>`;
    return;
  }

  target.innerHTML = awards.map((award, index) => `
    <article class="award-item" style="--award-delay:${Math.min(index, 5) * 55}ms">
      <div class="award-item-top">
        <span class="award-status">EARNED</span>
        <time datetime="${esc(award.date || "")}">${fmtDate(award.date)}</time>
      </div>
      <h5>${esc(award.name || "Unnamed Award")}</h5>
      ${award.hostedBy ? `<div class="award-host">Hosted by ${esc(award.hostedBy)}</div>` : ""}
    </article>
  `).join("");
}

function renderAwards(member){
  const allAwards = Array.isArray(state.data?.awards) ? state.data.awards : [];
  const memberId = normalize(member.id);
  const earned = allAwards.filter(award =>
    normalize(award.memberId) === memberId && normalize(award.status) === "EARNED"
  );

  animateCount($("crest-count"), member.crests);
  animateCount($("medallion-count"), member.medallion);

  const medallions = earned.filter(a => normalize(a.category) === "MEDALLION");
  const crests = earned.filter(a => normalize(a.category) === "CREST");
  const achievements = earned.filter(a => normalize(a.category) === "ACHIEVEMENT");

  renderAwardList("medallion-list", medallions, "NO MEDALLIONS RECORDED");
  renderAwardList("crest-list", crests, "NO CRESTS RECORDED");
  renderAwardList("achievement-list", achievements, "NO ACHIEVEMENTS RECORDED");

  const empty = $("awards-empty");
  if(empty) empty.classList.toggle("hidden", earned.length > 0);
}

function renderGuidelines(){
  const target = $("guidelines-list");
  const rules = Array.isArray(state.data?.bondGuidelines) ? state.data.bondGuidelines : [];
  if(!target) return;

  if(!rules.length){
    target.innerHTML = `<div class="source-note">No Bond earning guidelines are currently published.</div>`;
    return;
  }

  target.innerHTML = rules.map((rule, index) => `
    <article class="guideline-card" style="--guide-delay:${Math.min(index, 4) * 45}ms">
      <span>${esc(rule.label)}</span>
      <strong>${esc(rule.value)}</strong>
      <small>${esc(rule.detail)}</small>
    </article>
  `).join("");
}

function setStatusPill(status){
  const pill = $("member-status-pill");
  if(!pill) return;
  const normalized = normalize(status);
  pill.textContent = status || "—";
  pill.dataset.status = normalized || "UNKNOWN";
  pill.setAttribute("aria-label", `Member status: ${status || "Unknown"}`);
}

function showMember(member){
  const transactions = Array.isArray(state.data?.transactions)
    ? state.data.transactions.filter(t => normalize(t.memberId) === normalize(member.id))
    : [];

  $("member-name").textContent = member.name || "—";
  $("member-id-display").textContent = member.id || "—";
  $("member-rank").textContent = member.rank || "—";
  $("member-join-date").textContent = fmtDate(member.joinDate);
  setStatusPill(member.status);

  const net = Number(member.overallNet);
  $("net-bonds").innerHTML = `${Number.isFinite(net) ? money(net) : "—"} <small>💴</small>`;
  animateNumber($("net-summary"), member.overallNet);
  animateNumber($("earned"), member.monthlyEarned);
  animateNumber($("deductions"), member.deductions);
  animateNumber($("shop"), member.shopSpending);

  renderAwards(member);

  const activity = $("activity-list");
  if(Array.isArray(member.weeklyEntries) && member.weeklyEntries.length){
    activity.innerHTML = member.weeklyEntries.map((a, index) => `
      <div class="activity-row" style="--row-delay:${Math.min(index, 7) * 40}ms">
        <div class="activity-name">Bond Entry</div>
        <div class="meta">${esc(a.week)} · Entry #${esc(a.entry)}</div>
        <div class="meta">Recorded earnings</div>
        <div class="amount-positive">+${money(a.bonds)} 💴</div>
      </div>`).join("");
    $("activity-note").textContent = state.data?.activityLog?.length
      ? "Member-linked activity details are displayed from the approved activity source."
      : "The current Staff Records Activity Log does not contain a Member ID field, so activity names, dates, and types cannot be safely attributed to individual members. Bond earnings shown above come directly from the member Bond Record.";
  } else {
    activity.innerHTML = `<div class="source-note">No current Bond activity entries are recorded for this member.</div>`;
    $("activity-note").textContent = "";
  }

  const txList = $("transaction-list");
  if(transactions.length){
    txList.innerHTML = transactions.slice().sort((a,b) => String(b.date).localeCompare(String(a.date))).map((t, index) => `
      <div class="transaction-row" style="--row-delay:${Math.min(index, 7) * 40}ms">
        <div class="tx-date">${fmtDate(t.date)}</div>
        <div>
          <div class="tx-type">${esc(t.type)}</div>
          <div class="tx-desc">${esc(t.description || "No description")}</div>
        </div>
        <div class="tx-amount amount-negative">−${money(t.amount)} 💴</div>
      </div>`).join("");
  } else {
    txList.innerHTML = `<div class="source-note">No outgoing Bond transactions are recorded.</div>`;
  }

  const archive = state.data?.monthlyArchive?.[member.id] || {};
  const months = Object.entries(archive).filter(([,v]) => Number(v) !== 0);
  $("monthly-list").innerHTML = months.length
    ? months.map(([month,v], index) => `<div class="monthly-row" style="--row-delay:${Math.min(index, 5) * 40}ms"><span>${esc(month)}</span><strong>${money(v)} 💴</strong></div>`).join("")
    : `<div class="source-note">No finalized historical monthly archive entries are currently recorded.</div>`;

  const account = $("account");
  account.classList.remove("hidden");
  account.classList.remove("account-reveal");
  void account.offsetWidth;
  account.classList.add("account-reveal");
  account.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block:"start" });
}

$("lookup-form").addEventListener("submit", e => {
  e.preventDefault();
  const id = normalize($("member-id").value);
  const member = state.data?.members?.find(m => normalize(m.id) === id);

  if(!member){
    $("account").classList.add("hidden");
    $("lookup-message").textContent = "Member ID not found. Please use your official ELX Member ID.";
    return;
  }

  $("lookup-message").textContent = "";
  showMember(member);
});

const header = $("site-header");
let ticking = false;
window.addEventListener("scroll", () => {
  if(ticking) return;
  ticking = true;
  requestAnimationFrame(() => {
    header?.classList.toggle("is-scrolled", window.scrollY > 12);
    ticking = false;
  });
}, { passive:true });

renderGuidelines();
loadData().then(renderGuidelines).catch(err => {
  $("lookup-message").textContent = "The portal data could not be loaded. Please try again later.";
  console.error(err);
});

                                                                  
