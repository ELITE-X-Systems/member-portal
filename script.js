const state = { data: null };

const $ = (id) => document.getElementById(id);
const money = (n) => Number(n || 0).toLocaleString("en-US", {maximumFractionDigits: 0});
const count = (n) => String(Math.max(0, Number(n || 0))).padStart(2, "0");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
}[c]));
const fmtDate = (s) => {
  if (!s) return "—";
  const d = new Date(`${s}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? esc(s)
    : d.toLocaleDateString("en-US",{year:"numeric",month:"short",day:"numeric"});
};

const normalize = (s) => String(s ?? "").trim().toUpperCase();

async function loadData(){
  const res = await fetch("data.json", {cache:"no-store"});
  if(!res.ok) throw new Error("Data source unavailable.");
  state.data = await res.json();
}

function renderAwardList(targetId, awards, emptyText){
  const target = $(targetId);

  if(!target) return;

  if(!awards.length){
    target.innerHTML = `<div class="award-empty">${esc(emptyText)}</div>`;
    return;
  }

  target.innerHTML = awards.map(award => `
    <article class="award-item">
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

  /*
   * The public data generator only publishes EARNED awards.
   * This second check keeps the UI safe if older/mixed data.json
   * files contain PENDING or REVOKED records.
   */
  const earned = allAwards.filter(award =>
    normalize(award.memberId) === memberId &&
    normalize(award.status) === "EARNED"
  );

  const medallions = earned.filter(a => normalize(a.category) === "MEDALLION");
  const crests = earned.filter(a => normalize(a.category) === "CREST");
  const achievements = earned.filter(a => normalize(a.category) === "ACHIEVEMENT");

  $("crest-count").textContent = count(member.crests);
  $("medallion-count").textContent = count(member.medallion);

  renderAwardList("medallion-list", medallions, "No Medallions recorded.");
  renderAwardList("crest-list", crests, "No Crests recorded.");
  renderAwardList("achievement-list", achievements, "No Achievements recorded.");

  const empty = $("awards-empty");
  if(empty){
    empty.classList.toggle("hidden", earned.length > 0);
  }
}

function showMember(member){
  const transactions = Array.isArray(state.data?.transactions)
    ? state.data.transactions.filter(t => normalize(t.memberId) === normalize(member.id))
    : [];

  const deductions = transactions.filter(t => normalize(t.type) === "DEDUCTION");
  const shop = transactions.filter(t => normalize(t.type) === "SHOP PURCHASE");
  const shopSpending = shop.reduce((sum,t)=>sum + Number(t.amount||0),0);

  $("member-name").textContent = member.name;
  $("member-id-display").textContent = member.id;
  $("member-rank").textContent = member.rank || "—";
  $("member-id-status").textContent = member.idStatus || "—";
  $("member-status").textContent = member.status || "—";
  $("member-join-date").textContent = fmtDate(member.joinDate);
  $("net-bonds").innerHTML = `${money(member.overallNet)} <small>💴</small>`;
  $("net-summary").textContent = money(member.overallNet);
  $("earned").textContent = money(member.monthlyEarned);
  $("deductions").textContent = money(member.deductions ?? deductions.reduce((s,t)=>s+Number(t.amount||0),0));
  $("shop").textContent = money(member.shopSpending ?? shopSpending);

  renderAwards(member);

  const activity = $("activity-list");
  if(member.weeklyEntries?.length){
    activity.innerHTML = member.weeklyEntries.map(a => `
      <div class="activity-row">
        <div class="activity-name">Bond Entry</div>
        <div class="meta">${esc(a.week)} · Entry #${esc(a.entry)}</div>
        <div class="meta">Recorded earnings</div>
        <div class="amount-positive">+${money(a.bonds)} 💴</div>
      </div>`).join("");
    $("activity-note").textContent =
      state.data.activityLog?.length
      ? "Member-linked activity details are displayed from the approved activity source."
      : "The current Staff Records Activity Log does not contain a Member ID field, so activity names, dates, and types cannot be safely attributed to individual members. Bond earnings shown above come directly from the member Bond Record.";
  } else {
    activity.innerHTML = `<div class="source-note">No current Bond activity entries are recorded for this member.</div>`;
    $("activity-note").textContent = "";
  }

  const txList = $("transaction-list");
  if(transactions.length){
    txList.innerHTML = transactions.slice().sort((a,b)=>String(b.date).localeCompare(String(a.date))).map(t => `
      <div class="transaction-row">
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

  const archive = state.data.monthlyArchive?.[member.id] || {};
  const months = Object.entries(archive).filter(([,v]) => Number(v) !== 0);
  $("monthly-list").innerHTML = months.length
    ? months.map(([month,v]) => `<div class="monthly-row"><span>${esc(month)}</span><strong>${money(v)} 💴</strong></div>`).join("")
    : `<div class="source-note">No finalized historical monthly archive entries are currently recorded.</div>`;

  $("account").classList.remove("hidden");
  $("account").scrollIntoView({behavior:"smooth",block:"start"});
}

$("lookup-form").addEventListener("submit", e => {
  e.preventDefault();

  const id = $("member-id").value.trim().toUpperCase();
  const member = state.data?.members?.find(m => normalize(m.id) === id);

  if(!member){
    $("account").classList.add("hidden");
    $("lookup-message").textContent = "Member ID not found. Please use your official ELX Member ID.";
    return;
  }

  $("lookup-message").textContent = "";
  showMember(member);
});

loadData().catch(err => {
  $("lookup-message").textContent = "The portal data could not be loaded. Please try again later.";
  console.error(err);
});
