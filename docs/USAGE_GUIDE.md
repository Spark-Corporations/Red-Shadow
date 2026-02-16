# RedClaw v2.0 — Kullanım Kılavuzu

## 🔴 RedClaw Nedir?

RedClaw, **otonom bir penetrasyon testi ajanıdır**. AI destekli bir "beyin" (Kaggle Phi-4) ve 10 pentesting aracı (Nmap, Metasploit, SQLMap vb.) kullanarak hedefleri tarar, açıkları bulur ve raporlar.

---

## 🚀 Kurulum — Tek Komut

Claude Code nasıl çalışıyorsa:

```
npm install -g @anthropic-ai/claude-code   →  `claude` komutu hazır
```

RedClaw da aynı şekilde:

```bash
pip install redclaw                         →  `redclaw` komutu hazır
```

**Arka planda otomatik olan şeyler:**

| Adım | Ne Yapılır? | Ne Zaman? |
|------|-------------|-----------|
| Python bağımlılıkları | `pip` tarafından kurulur | `pip install` sırasında |
| `redclaw` komutu | PATH'e eklenir | `pip install` sırasında |
| `~/.redclaw/` dizini | Otomatik oluşturulur | İlk çalıştırmada |
| 10 pentesting aracı | Eksik olanlar kurulur | İlk çalıştırmada |
| Claude Code CLI | Otomatik kurulur | İlk çalıştırmada |
| Node.js | Yoksa otomatik kurulur | İlk çalıştırmada |

> Sonraki açılışlarda bootstrap atlanır (< 1 saniye).

### 🔗 ngrok Linkini Ayarla (Kaggle Phi-4 Backend)

RedClaw'ın beyni Kaggle'daki Phi-4 modeli. Bu modele erişmek için **ngrok URL'ini** ayarlaman lazım. **3 yöntem** var (birini seç):

**Yöntem 1: Ortam Değişkeni (en basit)**
```bash
# Windows PowerShell
$env:REDCLAW_LLM_URL = "https://XXXX-XX-XX-XX-XX.ngrok-free.app"

# Linux / macOS
export REDCLAW_LLM_URL="https://0b2f-34-29-72-116.ngrok-free.app"
```

**Yöntem 2: `.env` Dosyası (kalıcı)**

Proje dizininde `.env` dosyası oluştur:
```env
REDCLAW_LLM_URL=https://XXXX-XX-XX-XX-XX.ngrok-free.app
REDCLAW_LLM_MODEL=phi-4
```

**Yöntem 3: Config dosyası (gelişmiş)**

`~/.redclaw/config/settings.yaml`:
```yaml
llm:
  url: "https://XXXX-XX-XX-XX-XX.ngrok-free.app"
  model: "phi-4"
```

> [!IMPORTANT]
> ngrok URL'i her Kaggle oturumunda değişir. Yeni oturum açtığında güncelle.

### Geliştirici Modu

```bash
git clone https://github.com/sparkstack/redclaw.git
cd redclaw
pip install -e .    # Editable mode — değişiklikler anında yansır
```

---

## 📋 Kullanılabilir Komutlar

`pip install` sonrası bu komutlar otomatik olarak PATH'e eklenir:

```bash
redclaw                     # Ana CLI (interaktif veya subcommand)
redclaw skin                # Claude Code skin modu
redclaw skin 10.10.10.5     # Belirli hedefle skin modu
redclaw doctor              # Araç sağlık kontrolü
redclaw setup-tools         # Eksik araçları kur (genelde gerek kalmaz)
redclaw proxy               # Reverse proxy başlat
redclaw agent "scan X"      # Tek seferlik görev

# Kısayollar (standalone komutlar)
redclaw-doctor              # = redclaw doctor
redclaw-skin                # = redclaw skin

# Python modül olarak
python -m redclaw            # = redclaw
```

---

## 🎨 İki Çalışma Modu

### 1. `redclaw` — Standalone Mod

RedClaw'ın kendi Rich terminali. Direkt kullanırsın:

```
redclaw ❯ /scan 10.10.10.5
redclaw ❯ /findings
redclaw ❯ /exploit CVE-2021-44228
redclaw ❯ /report
```

### 2. `redclaw skin` — Claude Code Skin Modu

Claude Code'un TUI'sine RedClaw kimliğini enjekte eder:

```
redclaw skin 10.10.10.5
     │
     ▼
┌──────────────────────────────────────────────────┐
│  1. System Prompt → "Sen RedClaw v2.0'sın..."    │
│  2. Hooks → GuardianRails, loglama, checkpoint   │
│  3. MCP Config → 10 pentest aracı tanımı         │
│  4. Proxy → Kaggle Phi-4'e yönlendirme           │
│  5. `claude` CLI başlatılır                       │
└──────────────────────────────────────────────────┘
```

> Claude Code kurulu değilse **otomatik kurulur**. Manuel bir şey gerekmez.

---

## REPL Slash Komutları

İnteraktif modda (`redclaw`) kullanılır:

```
/scan         →  Hedefi tara (Nmap + Masscan)
/exploit      →  Açık istismar et (onay gerekir!)
/recon        →  Keşif (DNS, WHOIS, subdomain)
/report       →  Pentest raporu oluştur
/status       →  Pipeline durumu
/findings     →  Bulunan açıklar
/tools        →  10 MCP aracını listele
/skin         →  Claude Code skin moduna geç
/doctor       →  Araç sağlık kontrolü
/help         →  Tüm komutlar
/quit         →  Çıkış
```

---

## 🐳 Docker

Konteynerda tüm 10 araç önceden kurulu:

```bash
docker compose up -d
docker compose run redclaw
```

---

## ⚠️ Güvenlik

- **GuardianRails**: Tehlikeli komutlar otomatik engellenir
- **Exploitation** kullanıcı onayı gerektirir
- **Scope dışı** hedefler taranmaz
- Tüm aksiyonlar `~/.redclaw/logs/` altına loglanır

---

## Nasıl Çalışır? (Mimari)

```
pip install redclaw
       │
       ▼
┌─ pip (pyproject.toml) ─────────────────────────┐
│  1. Python bağımlılıkları kurulur               │
│  2. `redclaw` komutu PATH'e eklenir             │
│  3. Post-install: bootstrap tetiklenir          │
└─────────────────────────────────────────────────┘
       │
       ▼
┌─ Bootstrap (ilk çalıştırma) ───────────────────┐
│  1. ~/.redclaw/ oluştur                         │
│  2. Doctor: 10 aracı kontrol et                 │
│  3. Installer: eksik olanları kur               │
│  4. Claude Code CLI'yi kur (npm install -g)     │
│  5. .initialized marker yaz                     │
└─────────────────────────────────────────────────┘
       │
       ▼
┌─ Sonraki açılışlar ────────────────────────────┐
│  Marker var? → Araçlar hâlâ var mı? → HAZIR    │
│  (< 1 saniye)                                   │
└─────────────────────────────────────────────────┘
```
