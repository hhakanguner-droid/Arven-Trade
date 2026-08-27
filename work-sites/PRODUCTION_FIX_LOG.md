# ARVEN Trade — Production Fix Log

Bu kayıt, canlı Sites ortamında yapılan dar kapsamlı operasyonel düzeltmeleri izlemek için tutulur. Kod değişikliği yapılmayan, yalnızca canlı durum/veri kaydı onarımı içeren müdahaleler burada belgelenir.

## 2026-08-27 — GARAN stale analysis job temizliği

- **Canlı site:** `https://arven-trade.hhakanguner.chatgpt.site/`
- **Job ID:** `3515bb3a654c4b64afe4da81cb20ec3b`
- **Ticker:** `GARAN.IS`
- **Trade date:** `2026-08-27`
- **İlk durum:** `running`
- **İlk `updated_at`:** `2026-08-27T08:37:17.632Z`
- **Teşhis:** Aktif execution kalmadığı doğrulandı; D1 kaydı stale `running` durumunda kalmıştı. Tarayıcı polling yapmaya devam ettiği için UI analizi hâlâ çalışıyor gösteriyordu.
- **Müdahale:** Exact Job ID, kullanıcı, ticker, `running` durumu ve stale `updated_at` eşleşmesiyle sınırlandırılmış tek kullanımlık server-side D1 bakım endpoint’i kullanıldı.
- **Final durum:** `failed`
- **Final `updated_at`:** `2026-08-27T09:18:45.349Z`
- **Error type:** `AnalysisCancelled`
- **Error message:** `Analiz kullanıcı isteğiyle durduruldu.`
- **Result:** `null`
- **Maintenance endpoint:** İşlem sonrası kaldırıldı.
- **Requeue:** `false` — tekrar kuyruğa alınmadı.
- **Kalıcı kod değişikliği:** Yok.
- **Kapsam dışı bırakılanlar:** Diğer analysis job’ları, history, watchlist, KAP verisi ve uygulama ayarları değiştirilmedi.

### Takip notu

Bu olay, `running` job kayıtlarının aktif execution ile ayrıştırılabilmesi için ileride heartbeat/progress ve stale-job watchdog/timeout mekanizması eklenmesi gerektiğini gösterdi. Bu kayıt yalnızca mevcut operasyonel müdahaleyi belgeler.

## 2026-08-27 — Kalıcı koruma ve gerçek ajan ilerlemesi referans implementasyonu

GARAN olayının ardından `feature/work-sites-phase14` üzerinde Phase 13 Python davranış referansı için kalıcı koruma hazırlandı:

- analysis job şemasına additive progress/heartbeat/deadline alanları,
- `GET /api/v1/analyses/{job_id}` yanıtına güvenli `progress` nesnesi,
- gerçek LangGraph node boundary'lerinden dokuz kilitli ARVEN ajan adına progress mapping,
- heartbeat ile gerçek progress sinyalinin ayrıştırılması,
- 300 sn progress-stall ve 900 sn toplam analysis deadline varsayılanı,
- stalled job için `failed / AnalysisStalled`,
- hard timeout için `failed / AnalysisTimeout`,
- terminal durumdan sonra geç gelen success/failure yazısının `status='running'` koşuluyla engellenmesi,
- regresyon testleri,
- Sites-native karşılık için `work-sites/HOTFIX_PROGRESS_STALE_JOBS.md`,
- makine-okunur `work-sites/progress-contract.json`.

**Önemli:** Bu GitHub değişikliği canlı ChatGPT Site'a otomatik deploy edilmiş sayılmaz. Sites canlı runtime/D1/UI tarafındaki eşdeğer değişiklik Work/Sites tarafından uygulanıp smoke test edilmeden canlı koruma tamamlanmış kabul edilmemelidir.
