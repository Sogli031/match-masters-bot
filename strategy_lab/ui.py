"""Standalone local Tk screen. Worker process never imports the live runtime."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .catalog import ROOT, catalog, discover
from .experiment import DATA, create_job, pause, report, status
from .live import configure, profile_from_report, settings
from .policy import canonical


class Lab:
    def __init__(self, root):
        self.root=root; self.job=None; self.worker=None; self.groups=[]; self.result=None; self.busy=False
        self.inventory=catalog();self.booster_labels={a["key"]:a["label"] for a in self.inventory["boosters"]}
        root.title("Strategy Lab — Match Masters"); root.geometry("1180x850")
        frame=ttk.Frame(root,padding=12);frame.pack(fill="both",expand=True)
        ttk.Label(frame,text="Strategy Lab",font=("Segoe UI",20,"bold")).pack(anchor="w")
        ttk.Label(frame,text="Offline: B — odluke sa snimljenim setupom. A — rangiranje opreme i cele partije još nisu podržani.").pack(anchor="w")
        bar=ttk.Frame(frame);bar.pack(fill="x",pady=8)
        ttk.Label(bar,text="Datum snimaka (prazno = svi):").pack(side="left")
        self.day=tk.StringVar(value=datetime.date.today().isoformat())
        ttk.Entry(bar,textvariable=self.day,width=13).pack(side="left",padx=6)
        ttk.Button(bar,text="Učitaj instalaciju i snimke",command=self.discover).pack(side="left")
        self.level=tk.StringVar(value="quick")
        ttk.Combobox(bar,textvariable=self.level,values=("quick","detailed"),state="readonly",width=10).pack(side="right")
        ttk.Label(bar,text="Brza: 40 / detaljna: 200 tabli po modu  ").pack(side="right")
        tabs=ttk.Notebook(frame);tabs.pack(fill="both",expand=True)
        selection=ttk.Frame(tabs,padding=6);inventory=ttk.Frame(tabs,padding=6);results=ttk.Frame(tabs,padding=6)
        tabs.add(selection,text="1. Režimi, cilj i oprema");tabs.add(inventory,text="Podrška instalacije");tabs.add(results,text="2. Rezultati i live profil")
        ttk.Label(selection,text="Označite jednu ili više stvarno zabeleženih kombinacija (Ctrl/Shift). Slotovi ostaju deo setupa i posle trošenja.").pack(anchor="w")
        filters=ttk.Frame(selection);filters.pack(fill="x",pady=4)
        self.format=tk.StringVar(value="svi");self.mode=tk.StringVar(value="svi")
        self.format_box=ttk.Combobox(filters,textvariable=self.format,state="readonly",width=24)
        self.format_box.pack(side="left");self.format_box.bind("<<ComboboxSelected>>",lambda e:self.render_groups())
        self.mode_box=ttk.Combobox(filters,textvariable=self.mode,state="readonly",width=35)
        self.mode_box.pack(side="left",padx=8);self.mode_box.bind("<<ComboboxSelected>>",lambda e:self.render_groups())
        ttk.Button(filters,text="Označi sve prikazane",command=lambda:self.tree.selection_set(self.tree.get_children())).pack(side="left")
        self.tree=ttk.Treeview(selection,columns=("format","mode","goal","setup","n"),show="headings",selectmode="extended")
        for key,label,width in (("format","Format",130),("mode","Pravila table",185),("goal","Cilj",140),("setup","Booster / perk slotovi",470),("n","Snimci",60)):
            self.tree.heading(key,text=label);self.tree.column(key,width=width,stretch=key=="setup")
        self.tree.pack(fill="both",expand=True)
        scroll=ttk.Scrollbar(selection,orient="horizontal",command=self.tree.xview);scroll.pack(fill="x");self.tree.configure(xscrollcommand=scroll.set)
        inv=tk.Text(inventory,wrap="word",font=("Segoe UI",10));inv.pack(fill="both",expand=True)
        for section in ("modes","boosters","perks"):
            inv.insert("end",section.upper()+"\n\n")
            for row in self.inventory[section]:
                inv.insert("end",f"{row['label']} — {row['status']}\n{row['gap']}\n\n")
        inv.configure(state="disabled")
        self.result_groups=ttk.Combobox(results,state="readonly");self.result_groups.pack(fill="x")
        self.variant=tk.StringVar(value="direct")
        livebar=ttk.Frame(results);livebar.pack(fill="x",pady=6)
        ttk.Combobox(livebar,textvariable=self.variant,values=("direct","extra","charge"),state="readonly",width=12).pack(side="left")
        ttk.Button(livebar,text="Postojeća strategija",command=lambda:self.set_live("existing")).pack(side="left",padx=4)
        ttk.Button(livebar,text="Rad u senci",command=lambda:self.set_live("shadow")).pack(side="left",padx=4)
        ttk.Button(livebar,text="Aktivan eksperimentalni profil",command=lambda:self.set_live("active")).pack(side="left",padx=4)
        ttk.Label(results,text="Aktivni profil ima samo proveru uske mere. Nema potvrde boljeg rezultata cele partije. Nepodržano stanje vraća postojeću strategiju.").pack(anchor="w")
        self.output=tk.Text(results,wrap="word",font=("Consolas",10));self.output.pack(fill="both",expand=True)
        controls=ttk.Frame(frame);controls.pack(fill="x",pady=8)
        for label,cmd in (("Pokreni novi",self.new),("Pauziraj",self.pause),("Otvori posao…",self.open),("Nastavi",self.resume),("Otvori rezultate",self.results)):
            ttk.Button(controls,text=label,command=cmd).pack(side="left",padx=4)
        self.progress=ttk.Progressbar(frame,mode="determinate");self.progress.pack(fill="x")
        self.state=tk.StringVar(value="Učitajte snimke. Sve simulacije rade sa zatvorenom igrom.")
        ttk.Label(frame,textvariable=self.state,wraplength=1100).pack(anchor="w",pady=6)
        self.live_state=tk.StringVar();ttk.Label(frame,textvariable=self.live_state).pack(anchor="w")
        root.after(700,self.tick)

    def discover(self):
        if self.busy:return
        self.busy=True;self.state.set("Čitam snimke…")
        # Tk values are captured on the main thread before any background access.
        day=self.day.get().strip() or None
        def safe_work():
            try:
                groups=discover(ROOT/"Debug"/"runs",day)
                self.root.after(0,lambda:self.loaded(groups))
            except Exception as exc:self.root.after(0,lambda error=str(exc):self.error(error))
        threading.Thread(target=safe_work,daemon=True).start()

    def loaded(self,groups):
        self.groups=groups;self.busy=False
        self.format_box["values"]=["svi"]+sorted({g["identity"]["format"] for g in groups})
        self.mode_box["values"]=["svi"]+sorted({g["identity"]["mode"] for g in groups})
        self.render_groups();self.state.set(f"Pronađeno {len(groups)} kombinacija. solo_unclassified = Solo format čiji podtip snimak ne dokazuje.")

    def render_groups(self):
        self.tree.delete(*self.tree.get_children())
        for g in self.groups:
            i=g["identity"]
            if self.format.get() not in ("svi",i["format"]) or self.mode.get() not in ("svi",i["mode"]):continue
            setup=i["setup"];booster=setup["booster"]
            label=f"{self.booster_labels.get(booster,booster)} ({booster}) | "+" / ".join(setup["perks"])
            self.tree.insert("", "end",iid=g["key"],values=(i["format"],i["mode"],canonical(i["goal"]),label,g["records"]))

    def error(self,error):
        self.busy=False;self.state.set(error);messagebox.showerror("Strategy Lab",error)

    def new(self):
        keys=self.tree.selection()
        if not keys:return self.error("Označite bar jednu kombinaciju režima, cilja i setupa.")
        if self.busy:return
        path=filedialog.asksaveasfilename(initialdir=str(DATA),defaultextension=".sqlite",filetypes=[("Strategy Lab","*.sqlite")])
        if not path:return
        self.busy=True;self.state.set("Zamrzavam ulazne snimke za ponovljiv eksperiment…")
        day=self.day.get().strip() or None;level=self.level.get()
        def work():
            try:
                create_job(path,day=day,group_keys=keys,detail=level,limit=40 if level=="quick" else 200)
                self.root.after(0,lambda:self.start_created(Path(path)))
            except Exception as exc:self.root.after(0,lambda error=str(exc):self.error(error))
        threading.Thread(target=work,daemon=True).start()

    def start_created(self,path):
        self.job=path;self.busy=False;self.resume()

    def pause(self):
        if self.job:pause(self.job)

    def open(self):
        path=filedialog.askopenfilename(initialdir=str(DATA),filetypes=[("Strategy Lab","*.sqlite")])
        if path:self.job=Path(path);self.results()

    def resume(self):
        if not self.job:return self.error("Prvo otvorite sačuvani .sqlite posao.")
        if self.worker and self.worker.poll() is None:return
        DATA.mkdir(parents=True,exist_ok=True)
        # pythonw cannot print CLI progress to an absent console; use python.exe.
        executable=Path(sys.executable)
        if executable.name.lower()=="pythonw.exe":executable=executable.with_name("python.exe")
        with open(str(self.job)+".worker.log","a",encoding="utf-8") as log:
            self.worker=subprocess.Popen([str(executable),"-m","strategy_lab","resume",str(self.job)],cwd=ROOT,
                stdout=log,stderr=log,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))

    def results(self):
        if not self.job:return
        try:
            self.result=report(self.job)
            self.result_groups["values"]=[key+" | "+canonical(g["identity"]) for key,g in self.result["groups"].items()]
            if self.result_groups["values"]:self.result_groups.current(0)
            self.output.delete("1.0","end");self.output.insert("end",json.dumps(self.result,ensure_ascii=False,indent=2))
        except Exception as exc:self.error(str(exc))

    def set_live(self,mode):
        try:
            profile=None
            if mode!="existing":
                if not self.result or not self.result_groups.get():raise ValueError("Otvorite izveštaj i izaberite setup.")
                key=self.result_groups.get().split(" | ")[0]
                profile=profile_from_report(self.result,key,self.variant.get())
            configure(mode,profile)
        except Exception as exc:self.error(str(exc))

    def tick(self):
        cfg=settings();self.live_state.set("Live: "+cfg.get("mode","existing")+" / "+str((cfg.get("profile") or {}).get("variant","postojeća strategija")))
        if self.job and self.job.exists() and not self.busy:
            try:
                s=status(self.job);self.progress["maximum"]=max(1,s["total"]);self.progress["value"]=s["completed"]
                self.state.set(f"{self.job.name}: {s['status']} | kombinacije {s['completed_combinations']}/{s['combinations']} | table {s['completed']}/{s['total']} | procene profila {s['policy_evaluations']} | ETA {s['eta_seconds']} s")
                if self.worker and self.worker.poll() not in (None,0):
                    self.state.set("Worker je stao sa greškom; otvorite "+str(self.job)+".worker.log")
            except Exception:pass
        self.root.after(700,self.tick)


def show():
    root=tk.Tk();Lab(root);root.mainloop()
