# ARVEN Trade — Phase 14 Stale-Job + Gerçek Ajan İlerlemesi Hotfix

Bu belge, `feature/work-sites-phase14` içindeki Python servis değişikliklerinin **ChatGPT Sites canlı runtime karşılığını** tanımlar. GitHub ve Sites ayrı yayın yüzeyleridir; bu dosyanın commit edilmesi canlı siteyi tek başına güncellemez.

Canlı site: `https://arven-trade.hhakanguner.chatgpt.site/`

## Amaç

1. Bir analysis execution artık ilerlemiyorsa D1 kaydının süresiz `running` kalmasını engelle.
2. Kullanıcıya sahte timer/animasyon değil, gerçek server-side ajan/aşama ilerlemesini göster.
3. Timeout/stall sonrasında geç gelen sonuçların terminal job kaydını tekrar başarıya çevirmesini engelle.
4. Kullanıcı navigasyonunu kilitlemeden mevcut polling kontratını koru.

## 2026-08-27 regresyon vakası

Aşağıdaki olay artık regresyon testi olarak ele alınmalıdır:

- Job: `3515bb3a654c4b64afe4da81cb20ec3b`
- Ticker: `GARAN.IS`
- Stale durum: `running`
- Stale `updated_at`: `2026-08-27T08:37:17.632Z`
- Aktif execution: yok
- Operasyonel temizlik finali: `failed`
- Error: `AnalysisCancelled`
- Final `updated_at`: `2026-08-27T09:18:45.349Z`

Aynı semptom yeniden oluşmamalı: aktif/ilerleyen execution yokken UI süresiz `Çalışıyor` göstermemeli.

## D1 analysis_jobs alanları

Mevcut tabloyu additive migration ile genişlet. Var olan job/status/history kayıtlarını silme.

Gerekli alanlar:

- `current_agent`
- `progress_percent`
- `completed_agents_json`
- `heartbeat_at`
- `progress_at`
- `started_at`
- `deadline_at`
- `stale_after_at`
- mümkünse Sites execution lease için `execution_token` veya eşdeğer tahmin edilemez server-side lease kimliği

`status` kontratı değişmez:

`queued -> running -> succeeded | failed`

Yeni `cancelled` state ekleme.

## Gerçek ilerleme sinyali

İlerleme yalnızca gerçekten başlayan/tamamlanan server-side execution aşamalarından yazılmalıdır. Timer ile yüzde artırma, sahte tamamlanma veya browser tarafında tahmin yasaktır.

Kullanıcıya gösterilecek kilitli ARVEN ajan kimlikleri:

1. Piyasa Analisti
2. Duyarlılık Analisti
3. Haber Analisti
4. Temel Analist
5. KAP Araştırmacısı
6. Boğa Görüş Araştırmacısı
7. Ayı Görüş Araştırmacısı
8. Risk Yöneticisi
9. İşlem (Trader) Ajanı

Gerçek TradingAgents/LangGraph node eşlemesi:

- `Market Analyst` / `tools_market` -> `Piyasa Analisti`
- `Sentiment Analyst` / `tools_social` -> `Duyarlılık Analisti`
- `News Analyst` / `tools_news` -> `Haber Analisti`
- `Fundamentals Analyst` / `tools_fundamentals` -> `Temel Analist`
- `KAP Analyst` / `tools_kap` -> `KAP Araştırmacısı`
- `Bull Researcher` -> `Boğa Görüş Araştırmacısı`
- `Bear Researcher` -> `Ayı Görüş Araştırmacısı`
- `Trader` -> `İşlem (Trader) Ajanı`
- `Aggressive Analyst`, `Neutral Analyst`, `Conservative Analyst`, `Portfolio Manager` -> `Risk Yöneticisi`

Raw prompt, model reasoning veya chain-of-thought kaydetme/gösterme. Yalnızca güvenli stage adı, durum, zaman ve tamamlanma bilgisi tutulmalı.

## Heartbeat ve stall ayrımı

İki ayrı kavram kullan:

- `heartbeat_at`: execution hâlâ canlı/lease sahibi olduğunu gösterir.
- `progress_at`: gerçek bir node/tool/stage boundary ilerlemesi olduğunu gösterir.

Heartbeat, `stale_after_at` süresini **uzatmamalı**. Aksi halde provider çağrısında asılı kalan bir worker sonsuza kadar kendi heartbeat'iyle `running` kalabilir.

Önerilen varsayılanlar:

- heartbeat: 15 saniye
- progress stall timeout: 300 saniye
- toplam analysis hard timeout: 900 saniye

Bunlar server-side config/env ile değiştirilebilir olmalı; browser tarafından kontrol edilmemeli.

## Timeout davranışı

### Progress stall

`progress_at/stale_after_at` süresi dolarsa:

- gerçek execution abort/cancel edilmeye çalışılmalı,
- job atomik olarak `failed` yapılmalı,
- `error.type = "AnalysisStalled"`
- kullanıcı mesajı: `Analiz ilerlemesi zaman aşımına uğradı.`

### Hard timeout

Toplam `deadline_at` aşılırsa:

- gerçek execution abort/cancel edilmeli,
- job atomik olarak `failed` yapılmalı,
- `error.type = "AnalysisTimeout"`
- kullanıcı mesajı: `Analiz maksimum çalışma süresini aştı.`

Sites runtime destekliyorsa provider/fetch/LLM çağrılarında `AbortController` veya eşdeğer gerçek iptal mekanizması kullan. Sadece D1 durumunu değiştirmek yeterli sayılmaz; asılı execution yeni işleri bloke etmemeli.

## Late-write koruması

Her progress/heartbeat/success/failure yazısı:

- exact `job_id`
- `status = running`
- varsa current `execution_token/lease`

eşleşmesiyle koşullandırılmalı.

Bir timeout/stall/cancel terminal yazısından sonra eski execution'ın geç gelen sonucu `succeeded` yazamamalı.

## Restart / recovery

- `succeeded` ve `failed` hiçbir zaman tekrar kuyruğa alınmamalı.
- `running` kayıt yalnızca gerçekten geçerli/resumable execution lease/checkpoint varsa recovery almalı.
- Aktif execution/lease yoksa güvenli `failed` / `AnalysisInterrupted` durumuna geçir.
- Kör şekilde bütün `running` kayıtları `queued` yapma.
- Aynı idempotency key ile yeni duplicate execution yaratma.

## GET /api/arven/analyses/{job_id}

Mevcut alanlara ek olarak server response şu güvenli yapıyı döndürmeli:

```json
{
  "progress": {
    "current_agent": "Haber Analisti",
    "percent": 22,
    "completed_agents": [
      "Piyasa Analisti",
      "Duyarlılık Analisti"
    ],
    "heartbeat_at": "ISO-8601 UTC",
    "progress_at": "ISO-8601 UTC",
    "started_at": "ISO-8601 UTC",
    "deadline_at": "ISO-8601 UTC",
    "stale_after_at": "ISO-8601 UTC",
    "agents": [
      {"name": "Piyasa Analisti", "status": "completed"},
      {"name": "Duyarlılık Analisti", "status": "completed"},
      {"name": "Haber Analisti", "status": "running"},
      {"name": "Temel Analist", "status": "waiting"}
    ]
  }
}
```

`agents` listesinde canlı ürünün dokuz kilitli ajanı bulunmalı. Bir ajan gerçekten çalışmadıysa onu tamamlandı diye işaretleme.

## Hisse Analizi UI

Mevcut `Çalışıyor` kartının altında veya ajan kartlarının üstünde gerçek ilerleme alanı göster:

- genel yüzde/progress bar
- `Şu anda: Haber Analisti` gibi current agent
- dokuz ajan için:
  - `Tamamlandı`
  - `Çalışıyor`
  - `Bekliyor`
- mümkünse `Son gerçek ilerleme: xx sn önce`
- terminal `failed` olduğunda polling durmalı ve güvenli hata mesajı görünmeli
- terminal `succeeded` olduğunda progress `%100` ve sonuç ekranı açılmalı

Navigasyon analiz sırasında kullanılabilir kalmalı.

## Sites-native uygulama şartı

Python referans implementasyonu D1/Sites runtime'ın kendisi değildir. Canlı Site aynı davranışı Sites-native server code + D1 üzerinde uygulamalıdır.

Özellikle:

- client-side-only çözüm yapma,
- localStorage/IndexedDB ile job truth tutma,
- sahte interval progress yapma,
- bakım endpoint'ini kalıcı bırakma,
- provider secret'larını browser'a taşıma.

## Smoke / regresyon kontrolleri

Yayından önce en az:

1. Yeni test ticker job başlat.
2. `queued -> running` görülmeli.
3. `current_agent`, `progress_at`, `completed_agents` gerçekten değişmeli.
4. Aynı job polling sırasında yüzde monoton ilerlemeli; timer ile değil node eventleriyle.
5. Yapay stall testinde en geç configured stall timeout'ta `failed/AnalysisStalled`.
6. Hard-timeout testinde `failed/AnalysisTimeout`.
7. Timeout sonrası geç success yazısı terminal kaydı değiştirememeli.
8. Restart testinde terminal job requeue olmamalı.
9. Başka job/history/watchlist/KAP kayıtları etkilenmemeli.
10. Bakım/debug endpoint'i kalmamalı.

## Yayın raporu

Work/Sites uygulaması bittikten sonra yalnızca şunları raporla:

- Sites version/deploy SHA
- D1 migration uygulandı mı
- progress endpoint response örneği
- gerçek ajan progress smoke sonucu
- stall timeout smoke sonucu
- hard timeout smoke sonucu
- late-write/requeue koruması sonucu
- canlı URL
