/* ============================================================
   CRM_CSS companion script — Intelligence Console interactivity
   Vanilla JS. No framework. Demo data only — wire fetch() calls
   to your Supabase/SQLite API where marked TODO.
   ============================================================ */

/* ---------- Demo data (replace with API calls) ---------- */
const LEADS = [
  { id:1, name:"Apex Dental Clinic",     source:"Google Maps", score:92, temp:"hot",  status:"SQL",     owner:"Advit", touch:"2h ago",  stage:"sql",   acv:48000,  phone:"+91 98xxxxxx21", email:"contact@apexdental.in" , highlight:"Low review count + no active Meta Ads — strong GMB + lead-gen upsell fit."},
  { id:2, name:"Yamuna Realty Group",    source:"LinkedIn",    score:81, temp:"hot",  status:"MQL",     owner:"Advit", touch:"5h ago",  stage:"mql",   acv:120000, phone:"+91 99xxxxxx02", email:"info@yamunarealty.com", highlight:"Posted 'looking for lead-gen agency' on LinkedIn 3 days ago — high buying intent." },
  { id:3, name:"Gaur Coaching Center",   source:"Universal",   score:74, temp:"warm", status:"Prospect",owner:"Advit", touch:"1d ago",  stage:"prospect", acv:22000, phone:"+91 97xxxxxx88", email:"gaurcoaching@gmail.com", highlight:"Parent-niche match; no site speed issues but zero paid visibility." },
  { id:4, name:"Sharma Furnishings",     source:"Naukri",      score:58, temp:"warm", status:"Prospect",owner:"Ravi",  touch:"3d ago",  stage:"prospect", acv:15000, phone:"N/A",            email:"N/A", highlight:"Hiring a 'Digital Marketing Executive' — signal of upcoming ad spend." },
  { id:5, name:"Dr. Mehta Wellness",     source:"Google Maps", score:38, temp:"cold", status:"Nurture", owner:"Ravi",  touch:"9d ago",  stage:"lost",  acv:0,      phone:"+91 90xxxxxx14", email:"N/A", highlight:"Site is fast + modern, GMB healthy — low opportunity, deprioritized." },
  { id:6, name:"Expressway Properties",  source:"99acres",     score:66, temp:"warm", status:"SQL",     owner:"Advit", touch:"6h ago",  stage:"sql",   acv:75000,  phone:"+91 96xxxxxx45", email:"sales@expresswayprop.in", highlight:"Multiple resale listings near Yamuna Expressway — good fit for tracking audit." },
  { id:7, name:"Bright Future Academy",  source:"Shiksha",     score:85, temp:"hot",  status:"Won",     owner:"Advit", touch:"2d ago",  stage:"won",   acv:60000,  phone:"+91 95xxxxxx33", email:"admin@brightfuture.edu", highlight:"Closed — onboarded for SEO + local search package." },
  { id:8, name:"QuickBite Franchise",    source:"Google Maps", score:20, temp:"cold", status:"Lost",    owner:"Ravi",  touch:"14d ago", stage:"lost",  acv:0,      phone:"N/A", email:"N/A", highlight:"Went with an in-house team — logged for future re-engagement." },
];

const ACCOUNTS = [
  { name:"Apex Dental Clinic",    industry:"Healthcare",   deals:1, acv:48000,  health:"hot" },
  { name:"Yamuna Realty Group",   industry:"Real Estate",  deals:2, acv:195000, health:"hot" },
  { name:"Gaur Coaching Center",  industry:"Education",    deals:1, acv:22000,  health:"warm" },
  { name:"Expressway Properties", industry:"Real Estate",  deals:1, acv:75000,  health:"warm" },
  { name:"Bright Future Academy", industry:"Education",    deals:1, acv:60000,  health:"hot" },
];

const TASKS = [
  { title:"Follow up: Yamuna Realty — buying signal reply", meta:"Due today · Advit", overdue:false, done:false },
  { title:"Send audit PDF to Apex Dental Clinic",            meta:"Overdue by 1 day · Advit", overdue:true,  done:false },
  { title:"Call Sharma Furnishings re: hiring signal",       meta:"Overdue by 3 days · Ravi", overdue:true,  done:false },
  { title:"AI: review auto-drafted WA message for Gaur Coaching", meta:"Due today · Advit", overdue:false, done:false },
  { title:"Log outcome for Dr. Mehta Wellness",               meta:"Due tomorrow · Ravi", overdue:false, done:true },
];

const STAGE_ORDER = [
  { key:"prospect", label:"Prospect" },
  { key:"mql",       label:"MQL" },
  { key:"sql",       label:"SQL" },
  { key:"won",        label:"Won" },
  { key:"lost",       label:"Lost" },
];

const tempTagClass = { hot:"crm-tag--hot", warm:"crm-tag--warm", cold:"crm-tag--cold" };
const money = n => n ? "₹" + n.toLocaleString("en-IN") : "—";

/* ---------- View switching ---------- */
const titles = {
  pipeline:"Pipeline", leads:"All Leads", accounts:"Accounts",
  tasks:"Tasks & Rules", reports:"Reports", automation:"Automation"
};
document.querySelectorAll(".crm-nav__item").forEach(item=>{
  item.addEventListener("click", ()=>{
    document.querySelectorAll(".crm-nav__item").forEach(i=>i.classList.remove("is-active"));
    item.classList.add("is-active");
    const view = item.dataset.view;
    document.querySelectorAll(".crm-view").forEach(v=>v.classList.remove("is-active"));
    document.getElementById("view-"+view).classList.add("is-active");
    document.getElementById("crm-title").textContent = titles[view] || view;
  });
});

/* ---------- Signal strip ---------- */
function renderSignalStrip(){
  const strip = document.getElementById("crm-signalstrip");
  strip.innerHTML = "";
  // 60 ticks sampled/weighted from lead temperatures
  const weighted = [];
  LEADS.forEach(l=>{ for(let i=0;i<8;i++) weighted.push(l.temp); });
  while(weighted.length < 60) weighted.push("idle");
  weighted.slice(0,60).sort(()=>Math.random()-0.5).forEach(t=>{
    const i = document.createElement("i");
    i.className = t;
    strip.appendChild(i);
  });
}

/* ---------- Kanban ---------- */
function renderKanban(){
  const board = document.getElementById("crm-kanban");
  board.innerHTML = "";
  STAGE_ORDER.forEach(stage=>{
    const items = LEADS.filter(l=>l.stage===stage.key);
    const col = document.createElement("div");
    col.className = "crm-kcol";
    col.dataset.stage = stage.key;
    col.innerHTML = `
      <div class="crm-kcol__head">
        <span class="name">${stage.label}</span>
        <span class="count">${items.length}</span>
      </div>
      ${items.map(l=>`
        <div class="crm-card" data-id="${l.id}">
          <div class="crm-card__top">
            <span class="crm-card__name">${l.name}</span>
            <span class="crm-tag ${tempTagClass[l.temp]}">${l.temp}</span>
          </div>
          <div class="crm-card__meta">
            <span>${l.source}</span>
            <span class="crm-card__acv">${money(l.acv)}</span>
          </div>
        </div>
      `).join("") || `<div class="crm-empty" style="padding:20px 10px;">No leads in this stage</div>`}
    `;
    board.appendChild(col);
  });
  board.querySelectorAll(".crm-card").forEach(card=>{
    card.addEventListener("click", ()=>openModal(Number(card.dataset.id)));
  });
}

/* ---------- Leads table ---------- */
function renderLeadsTable(){
  const body = document.getElementById("crm-leads-body");
  body.innerHTML = LEADS.map(l=>`
    <tr data-id="${l.id}">
      <td>
        <span class="crm-dot ${l.temp}"></span>
        <span class="crm-cell-name">${l.name}</span>
        <div class="crm-cell-sub">${l.email}</div>
      </td>
      <td>${l.source}</td>
      <td class="crm-score">${l.score}</td>
      <td><span class="crm-tag ${tempTagClass[l.temp]}">${l.status}</span></td>
      <td>${l.owner}</td>
      <td class="crm-cell-sub">${l.touch}</td>
    </tr>
  `).join("");
  body.querySelectorAll("tr").forEach(row=>{
    row.addEventListener("click", ()=>openModal(Number(row.dataset.id)));
  });
}

/* ---------- Accounts table ---------- */
function renderAccounts(){
  const body = document.getElementById("crm-accounts-body");
  body.innerHTML = ACCOUNTS.map(a=>`
    <tr>
      <td class="crm-cell-name">${a.name}</td>
      <td>${a.industry}</td>
      <td>${a.deals}</td>
      <td>${money(a.acv)}</td>
      <td><span class="crm-tag ${tempTagClass[a.health]}">${a.health}</span></td>
    </tr>
  `).join("");
}

/* ---------- Tasks ---------- */
function renderTasks(){
  const list = document.getElementById("crm-task-list");
  list.innerHTML = TASKS.map(t=>`
    <div class="crm-task">
      <div class="crm-checkbox ${t.done ? "done":""}"></div>
      <div class="crm-task__body">
        <div class="crm-task__title">${t.title}</div>
        <div class="crm-task__meta ${t.overdue ? "overdue":""}">${t.meta}</div>
      </div>
    </div>
  `).join("");
}

/* ---------- Reports ---------- */
function renderReports(){
  const stageBars = document.getElementById("crm-stage-bars");
  const maxAcv = Math.max(...STAGE_ORDER.map(s=>LEADS.filter(l=>l.stage===s.key).reduce((a,l)=>a+l.acv,0)), 1);
  stageBars.innerHTML = STAGE_ORDER.map(s=>{
    const total = LEADS.filter(l=>l.stage===s.key).reduce((a,l)=>a+l.acv,0);
    const pct = Math.round((total/maxAcv)*100);
    return `
      <div class="crm-bar">
        <div class="crm-bar__label">${s.label}</div>
        <div class="crm-bar__track"><div class="crm-bar__fill" style="width:${pct}%"></div></div>
        <div class="crm-bar__val">${money(total)}</div>
      </div>`;
  }).join("");

  const sources = {};
  LEADS.forEach(l=>{ sources[l.source] = (sources[l.source]||0)+1; });
  const maxCount = Math.max(...Object.values(sources), 1);
  const sourceBars = document.getElementById("crm-source-bars");
  sourceBars.innerHTML = Object.entries(sources).map(([src,count])=>`
    <div class="crm-bar">
      <div class="crm-bar__label">${src}</div>
      <div class="crm-bar__track"><div class="crm-bar__fill" style="width:${Math.round((count/maxCount)*100)}%"></div></div>
      <div class="crm-bar__val">${count}</div>
    </div>
  `).join("");
}

/* ---------- Modal ---------- */
const modal = document.getElementById("crm-modal");
function openModal(id){
  const l = LEADS.find(x=>x.id===id);
  if(!l) return;
  document.getElementById("crm-modal-name").textContent = l.name;
  document.getElementById("crm-modal-sub").textContent = `${l.source} · Owner: ${l.owner}`;
  document.getElementById("crm-modal-highlight").textContent = l.highlight;
  document.getElementById("crm-modal-score").textContent = l.score + " / 100";
  document.getElementById("crm-modal-stage").textContent = l.status;
  document.getElementById("crm-modal-source").textContent = l.source;
  document.getElementById("crm-modal-phone").textContent = l.phone;
  document.getElementById("crm-modal-email").textContent = l.email;
  modal.classList.add("is-open");
}
document.getElementById("crm-modal-close").addEventListener("click", ()=>modal.classList.remove("is-open"));
modal.addEventListener("click", e=>{ if(e.target===modal) modal.classList.remove("is-open"); });
document.addEventListener("keydown", e=>{ if(e.key==="Escape") modal.classList.remove("is-open"); });

document.getElementById("crm-add-lead").addEventListener("click", ()=>{
  // TODO: replace with a real "create lead" form → POST to your Supabase/SQLite API
  alert("Hook this button to your lead-creation API (Supabase insert into `leads`).");
});

/* ---------- Init ---------- */
renderSignalStrip();
renderKanban();
renderLeadsTable();
renderAccounts();
renderTasks();
renderReports();
