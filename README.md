# 🌬️ Vestel AC — Home Assistant Integration

<p align="center">
  <a href="#english">🇬🇧 English</a>
  &nbsp; | &nbsp;
  <a href="#türkçe">🇹🇷 Türkçe</a>
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=mutlutekir&repository=Vestel_Klima_AirCon&category=integration">
    <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Install with HACS">
  </a>
  &nbsp;
  <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=vestel_ac">
    <img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Add to Home Assistant">
  </a>
</p>

---

<a id="english"></a>

# 🇬🇧 English

Vestel AC is an unofficial Home Assistant custom integration for Wi-Fi enabled Vestel Doğa / Flora series air conditioners.

It communicates directly with the Vestel Smart Life cloud API and provides advanced controls that are not normally exposed by Home Assistant.

> ⚠️ This is an unofficial community project and is not affiliated with Vestel.

## ✨ Features

- 🌡️ Cooling, heating, dry, fan-only and auto modes
- 🎯 Target temperature control
- 🌀 Auto + 1-5 fan speeds
- ↕️ Vertical louver position control
- 🔄 Vertical swing / stop swing
- ↔️ Horizontal louver support where available
- ⚡ Turbo mode
- 🌙 Sleep mode
- 🍃 Eco / Energy Saving mode
- ✨ Ionizer
- ⏰ Automatic shutdown timer
- 🩺 Diagnostic information
- 🌫️ VOC / particle air-quality information on supported models
- 🧹 Filter / particle-sensor lifetime information where available
- 🧪 Raw API status and command services
- 🔐 Automatic authentication with Vestel account credentials

---

## 🚀 Installation

### HACS — Recommended

<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=mutlutekir&repository=Vestel_Klima_AirCon&category=integration">
  <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Install with HACS">
</a>

Or manually:

1. Open HACS → Integrations.
2. Open ⋮ → Custom repositories.
3. Add:

    https://github.com/mutlutekir/Vestel_Klima_AirCon

4. Select **Integration**.
5. Install **Vestel AC**.
6. Restart Home Assistant.

### Manual

Download the latest release and copy:

    custom_components/vestel_ac

to:

    /config/custom_components/

Then restart Home Assistant.

---

## ⚙️ Configuration

Go to:

    Settings → Devices & Services → Add Integration

Search for:

    Vestel AC

The integration supports:

- Username / password login
- Refresh-token authentication as a fallback

After authentication, available Vestel air conditioners are automatically discovered.

---

## 🎛️ Supported Controls

| Feature | Support |
|---|:---:|
| Auto | ✅ |
| Cooling | ✅ |
| Heating | ✅ |
| Dry | ✅ |
| Fan Only | ✅ |
| Off | ✅ |
| Target Temperature | ✅ |
| Fan Auto / 1-5 | ✅ |
| Vertical Louver | ✅ |
| Vertical Swing | ✅ |
| Horizontal Louver | ⚠️ Model dependent |
| Turbo | ✅ |
| Sleep | ✅ |
| Eco | ✅ |
| Ionizer | ✅ |
| Auto Off Timer | ✅ |
| Diagnostics | ✅ |
| VOC / PM | ⚠️ Model dependent |
| Filter Lifetime | ⚠️ Model dependent |

---

## 🔬 Reverse-Engineered Parameters

The following values were identified from the Vestel Smart Life APK and verified against a real air conditioner.

### ACCMODE

| Value | Mode |
|---:|---|
| `0` | Auto |
| `1` | Cooling |
| `2` | Dry |
| `3` | Fan Only |
| `4` | Heating |
| `5` | Off |

### ACGENSI

The mode and fan speed are combined using:

    ACGENSI = ACCMODE + FanSpeed × 8

### ACFANPO

`ACFANPO` contains several settings as bit fields:

| Bits | Function |
|---|---|
| 0 | Turbo |
| 1-3 | Vertical louver |
| 4-6 | Horizontal louver |
| 7 | Sleep |
| 8 | Ionizer |
| 9 | Eco |

Vertical louver values:

| Value | Position |
|---:|---|
| `0` | Stop |
| `1` | Position 1 |
| `2` | Position 2 |
| `3` | Position 3 |
| `4` | Position 4 |
| `5` | Position 5 |
| `6` | Swing |

### Verified Vertical Louver Values

| Function | ACFANPO |
|---|---:|
| Top position | `00050` |
| Position 2 | `00052` |
| Position 3 | `00054` |
| Position 4 | `00056` |
| Bottom position | `00058` |
| Swing | `00060` |
| Stop / fixed position | `00048` |

### Verified Special Modes

| Function | Value |
|---|---:|
| Normal | `00050` |
| Sleep | `00178` |
| Ionizer | `00306` |
| Eco | `00562` |

Turbo is reflected in the `ACGENSI` state and was observed as:

    ACGENSI = 00025

---

## ⏰ Automatic Shutdown

`ACOFFTV` stores the automatic shutdown time:

    ACOFFTV = (minutes << 5) | hours

The value:

    2047

means the timer is disabled.

Example:

    14:18 → 00590

---

## 🩺 Diagnostic Data

The APK exposes additional diagnostic fields. Availability depends on the air-conditioner model and firmware.

| Field | Description |
|---|---|
| `ACERROR` | Error information |
| `ACERRTW` | UVC / particle sensor errors |
| `ACWARNG` | Warning information |
| `ACPOLVC` | VOC air quality |
| `ACPOLPM` | Particle / PM air quality |
| `ACOAFLP` | Odor & allergen filter lifetime |
| `ACPSCLP` | Particle sensor lifetime |
| `ACSAFRS` | Filter / sensor reset |
| `ACVERSI` | Firmware information |

Some fields may not be returned by the device. Missing capabilities are therefore not considered an error.

---

## 🔀 Multi-Appliance Support (fridges & other devices)

The Vestel Smart Life cloud serves every appliance type through the same endpoints. As of v1.1.0, the integration no longer assumes your account only contains air conditioners:

- AC entities (climate, louver, turbo/sleep/ionizer/eco switches, auto-off timer) are created **only** for air conditioners.
- Other appliances (e.g. Vestel fridges) appear as a normal device with **raw diagnostic sensors** for every field the cloud returns - ideal for feature discovery.
- One failing or unsupported appliance no longer breaks the whole integration (previously a fridge on the account caused a `KeyError: 'ACGENSI'` setup failure).

### Fridge support (work in progress)

A real Vestel fridge returns a field set that all starts with `RF`, so the integration detects it automatically and, instead of exposing it as an AC, creates the following on the fridge device:

- **door binary sensors** - `Soğutucu Kapısı` and `Dondurucu Kapısı`;
- decoded **temperature sensors** - `Soğutucu Sıcaklığı` and `Dondurucu Sıcaklığı` (in °C);
- read-only **mode binary sensors** - `Tatil Modu`, `Ekonomi Modu`, `Hızlı Soğutma`, `Hızlı Dondurma`, `Çocuk Kilidi` and `Ekran Koruyucu`.

| Field | Meaning | Status |
| --- | --- | --- |
| `RFDOORA` | Door state - a 2-bit field, one bit per door: `00003` (0b11) both closed, `00001` (0b01) fridge door open, `00002` (0b10) freezer door open (confirmed on a live device: the fridge alarmed ~2 min after the fridge door was left open) | **decoded** -> `Soğutucu Kapısı` + `Dondurucu Kapısı` binary sensors |
| `RFTEMSE` | Temperature setpoints - bit-packed, **not** two decimal halves: high byte = cooler °C, low byte = absolute freezer °C, i.e. `RFTEMSE = (cooler << 8) \| abs(freezer)`. E.g. `00528` (0x210) = +2 °C / -16 °C, `01304` (0x518) = +5 °C / -24 °C (confirmed against a 15-point calibration table) | **decoded** -> `Soğutucu Sıcaklığı` + `Dondurucu Sıcaklığı` temperature sensors |
| `RFMODEA` | Mode bit field - one bit per mode: `00002` (bit 1) fast freeze, `00004` (bit 2) fast cool, `00008` (bit 3) holiday, `00016` (bit 4) eco. The bits combine, e.g. `00006` = fast cool + fast freeze | **decoded** -> `Tatil Modu` / `Ekonomi Modu` / `Hızlı Soğutma` / `Hızlı Dondurma` binary sensors |
| `RFSSAVE` | Screen saver - `00000` off, `00001` on | **decoded** -> `Ekran Koruyucu` binary sensor |
| `RFDCOOL` | Fast cool | undecoded |
| `RFDEFEC` | Defrost | undecoded |
| `RFCOOER` | Cooler | undecoded |
| `RFCLOCK` | Child lock - `00000` off, `00001` on | **decoded** -> `Çocuk Kilidi` binary sensor |
| `WIFIRSS` / `WIFISET` | Wi-Fi signal / settings | raw |

Two modes also change what the fridge's own panel displays, and the temperature sensors mirror that: with **eco** on they report `E` for both setpoints (instead of a °C number), and with **holiday** on the cooler is switched off so `Soğutucu Sıcaklığı` reports *unknown* (`--`) while the freezer keeps its setpoint. The decoded numbers stay available in the raw `RFTEMSE` sensor and in each temperature sensor's attributes.

Fridge *controls* (setting the temperature, toggling eco, ...) are not implemented yet - the modes above are therefore read-only binary sensors. The command format is undocumented and the integration currently always sends `device_type: "AC"`. Use the **Feature Discovery** workflow below to decode them - anything you find is welcome as a PR.

## 🧪 Raw API Services

For advanced testing and feature discovery, the integration provides raw API services.

### Dump current device status

    vestel_ac.dump_raw_status

### Send a raw command

    vestel_ac.send_raw_code

Example:

    action: vestel_ac.send_raw_code
    data:
      code: "ACFANPO00562"

These services are mainly intended for development and reverse engineering.

> ⚠️ Do not send unknown values to the device. Incorrect commands may change its operating state.

---

## 🔍 Feature Discovery

New features can be investigated by comparing the raw status before and after changing a setting in the official Vestel application.

Recommended workflow:

    dump_raw_status
          ↓
    Change one setting
          ↓
    dump_raw_status
          ↓
    Compare changed fields
          ↓
    Test the discovered value
          ↓
    Add the feature to Home Assistant

---

## ❤️ Credits

**Home Assistant integration:**  
Mutlu Tekir

**Original Vestel API research:**  
Sezer İltekin

**Original project:**  
https://github.com/iltekin/vestel-ac-remote-control

The original API research provided the foundation for communicating with the Vestel cloud service. This integration extends that work with Home Assistant support and additional features discovered through APK analysis and real-device testing.

---

## ⚠️ Disclaimer

This project is unofficial and is not affiliated with Vestel.

The integration relies on the Vestel cloud API. API changes, authentication changes or service shutdowns by Vestel may cause the integration to stop working.

Some features are model and firmware dependent.

If you encounter a problem, please open an issue:

https://github.com/mutlutekir/Vestel_Klima_AirCon/issues

Do not include passwords, access tokens or refresh tokens in issue reports.

---

<a id="türkçe"></a>

# 🇹🇷 Türkçe

Vestel AC, Wi-Fi destekli Vestel Doğa / Flora serisi klimaları Home Assistant üzerinden kontrol etmek için geliştirilmiş resmi olmayan bir özel entegrasyondur.

Vestel Akıllı Yaşam bulut API'si ile doğrudan iletişim kurar ve Home Assistant'ta normalde bulunmayan gelişmiş klima kontrollerini sunar.

> ⚠️ Bu proje resmi değildir ve Vestel ile herhangi bir bağlantısı yoktur.

## ✨ Özellikler

- 🌡️ Soğutma, ısıtma, nem alma, fan ve otomatik mod
- 🎯 Hedef sıcaklık kontrolü
- 🌀 Auto + 1-5 fan hızı
- ↕️ Dikey kanatçık pozisyonu
- 🔄 Dikey salınım / salınımı durdurma
- ↔️ Desteklenen modellerde yatay kanatçık
- ⚡ Turbo
- 🌙 Uyku
- 🍃 Tasarruf / Eco
- ✨ İyonizer
- ⏰ Otomatik kapatma zamanlayıcısı
- 🩺 Tanı / hata bilgileri
- 🌫️ Desteklenen modellerde VOC / partikül hava kalitesi
- 🧹 Desteklenen modellerde filtre / partikül sensörü ömrü
- 🧪 Ham API durum ve komut servisleri
- 🔐 Vestel hesabıyla otomatik kimlik doğrulama

---

## 🚀 Kurulum

### HACS — Önerilen

<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=mutlutekir&repository=Vestel_Klima_AirCon&category=integration">
  <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="HACS ile yükle">
</a>

Alternatif olarak:

1. Home Assistant'ta HACS → Integrations bölümünü açın.
2. Sağ üstten ⋮ → Custom repositories seçin.
3. Aşağıdaki adresi ekleyin:

    https://github.com/mutlutekir/Vestel_Klima_AirCon

4. Kategori olarak **Integration** seçin.
5. **Vestel AC** entegrasyonunu yükleyin.
6. Home Assistant'ı yeniden başlatın.

### Manuel

Son sürümü indirin ve:

    custom_components/vestel_ac

klasörünü:

    /config/custom_components/

içine kopyalayın.

Ardından Home Assistant'ı yeniden başlatın.

---

## ⚙️ Yapılandırma

Şuraya gidin:

    Ayarlar → Cihazlar ve Hizmetler → Entegrasyon Ekle

Aratın:

    Vestel AC

Kimlik doğrulama için:

- Kullanıcı adı / şifre
- Yedek olarak Refresh Token

kullanılabilir.

Kimlik doğrulama tamamlandıktan sonra kullanılabilir Vestel klimalar otomatik olarak keşfedilir.

---

## 🎛️ Desteklenen Kontroller

| Özellik | Destek |
|---|:---:|
| Otomatik | ✅ |
| Soğutma | ✅ |
| Isıtma | ✅ |
| Nem Alma | ✅ |
| Sadece Fan | ✅ |
| Kapalı | ✅ |
| Hedef Sıcaklık | ✅ |
| Fan Auto / 1-5 | ✅ |
| Dikey Kanatçık | ✅ |
| Dikey Salınım | ✅ |
| Yatay Kanatçık | ⚠️ Modele bağlı |
| Turbo | ✅ |
| Uyku | ✅ |
| Tasarruf | ✅ |
| İyonizer | ✅ |
| Otomatik Kapatma | ✅ |
| Tanı Bilgileri | ✅ |
| VOC / PM | ⚠️ Modele bağlı |
| Filtre Ömrü | ⚠️ Modele bağlı |

---

## 🔬 Çözümlenen Parametreler

Bu değerler Vestel Akıllı Yaşam APK'sından araştırılmış ve gerçek bir klima üzerinde doğrulanmıştır.

### ACCMODE

| Değer | Mod |
|---:|---|
| `0` | Otomatik |
| `1` | Soğutma |
| `2` | Nem Alma |
| `3` | Sadece Fan |
| `4` | Isıtma |
| `5` | Kapalı |

### ACGENSI

Mod ve fan hızı birlikte kodlanır:

    ACGENSI = ACCMODE + FanSpeed × 8

### ACFANPO

| Bitler | Özellik |
|---|---|
| 0 | Turbo |
| 1-3 | Dikey kanatçık |
| 4-6 | Yatay kanatçık |
| 7 | Uyku |
| 8 | İyonizer |
| 9 | Tasarruf |

Dikey kanatçık:

| Değer | Pozisyon |
|---:|---|
| `0` | Durdur |
| `1` | 1. kademe |
| `2` | 2. kademe |
| `3` | 3. kademe |
| `4` | 4. kademe |
| `5` | 5. kademe |
| `6` | Salınım |

### Doğrulanmış Dikey Kanatçık Değerleri

| İşlev | ACFANPO |
|---|---:|
| En üst | `00050` |
| 2. kademe | `00052` |
| 3. kademe | `00054` |
| 4. kademe | `00056` |
| En alt | `00058` |
| Salınım | `00060` |
| Salınımı durdur | `00048` |

### Doğrulanmış Özel Modlar

| İşlev | Değer |
|---|---:|
| Normal | `00050` |
| Uyku | `00178` |
| İyonizer | `00306` |
| Tasarruf | `00562` |

Turbo için gerçek cihazda:

    ACGENSI = 00025

değeri gözlemlenmiştir.

---

## ⏰ Otomatik Kapatma

`ACOFFTV` otomatik kapanma saatini tutar:

    ACOFFTV = (dakika << 5) | saat

    2047 = zamanlayıcı kapalı

Örneğin:

    14:18 → 00590

---

## 🩺 Tanı Bilgileri

APK içerisinde aşağıdaki alanlar tespit edilmiştir. Kullanılabilirlik klima modeline ve firmware'e bağlıdır.

| Alan | Açıklama |
|---|---|
| `ACERROR` | Hata bilgisi |
| `ACERRTW` | UVC / partikül sensörü hatası |
| `ACWARNG` | Uyarı |
| `ACPOLVC` | VOC hava kalitesi |
| `ACPOLPM` | Partikül / PM hava kalitesi |
| `ACOAFLP` | Koku & alerjen filtre ömrü |
| `ACPSCLP` | Partikül sensörü ömrü |
| `ACSAFRS` | Filtre / sensör sıfırlama |
| `ACVERSI` | Firmware bilgisi |

Bazı cihazlarda bu alanlar hiç bulunmayabilir. Bu durumda ilgili özelliklerin kullanılamaması normaldir.

---

## 🔀 Çoklu Cihaz Desteği (buzdolabı ve diğer cihazlar)

Vestel Akıllı Yaşam bulutu, tüm cihaz tiplerine aynı uç noktalar üzerinden hizmet verir. v1.1.0 itibarıyla entegrasyon, hesabınızda sadece klima olduğunu varsaymıyor:

- Klima varlıkları (iklim, kanatçık, turbo/uyku/iyonizer/tasarruf anahtarları, otomatik kapatma) **yalnızca klimalar** için oluşturulur.
- Diğer cihazlar (ör. Vestel buzdolabı), bulutun döndürdüğü her alan için **ham tanı sensörleriyle** birlikte normal bir cihaz olarak görünür - özellik keşfi için idealdir.
- Tek bir cihazın hatası veya desteklenmemesi artık tüm entegrasyonu bozmaz (daha önce hesapta buzdolabı olması `KeyError: 'ACGENSI'` kurulum hatasına yol açıyordu).

### Buzdolabı desteği (geliştirme aşamasında)

Gerçek bir Vestel buzdolabı, tamamı `RF` ile başlayan bir alan kümesi döndürüyor; entegrasyon bunu otomatik algılıyor ve cihazı klima gibi göstermek yerine buzdolabı cihazı üzerinde şunları oluşturuyor:

- **kapı binary sensörleri** - `Soğutucu Kapısı` ve `Dondurucu Kapısı`;
- çözülmüş **sıcaklık sensörleri** - `Soğutucu Sıcaklığı` ve `Dondurucu Sıcaklığı` (°C);
- salt okunur **mod binary sensörleri** - `Tatil Modu`, `Ekonomi Modu`, `Hızlı Soğutma`, `Hızlı Dondurma`, `Çocuk Kilidi` ve `Ekran Koruyucu`.

| Alan | Anlamı | Durum |
| --- | --- | --- |
| `RFDOORA` | Kapı durumu - kapı başına bir bitlik 2 bitlik alan: `00003` (0b11) ikisi de kapalı, `00001` (0b01) buzdolabı kapağı açık, `00002` (0b10) dondurucu kapağı açık (gerçek cihazda doğrulandı: buzdolabı kapağı açık bırakılınca ~2 dk sonra cihaz alarm verdi) | **çözüldü** -> `Soğutucu Kapısı` + `Dondurucu Kapısı` binary sensörleri |
| `RFTEMSE` | Sıcaklık ayarları - bit paketli, **iki ondalık yarım değil**: yüksek bayt = soğutucu °C, düşük bayt = dondurucunun mutlak değeri °C, yani `RFTEMSE = (cooler << 8) \| abs(freezer)`. Ör. `00528` (0x210) = +2 °C / -16 °C, `01304` (0x518) = +5 °C / -24 °C (15 noktalı kalibrasyon tablosuyla doğrulandı) | **çözüldü** -> `Soğutucu Sıcaklığı` + `Dondurucu Sıcaklığı` sıcaklık sensörleri |
| `RFMODEA` | Mod bit alanı - her mod için bir bit: `00002` (bit 1) hızlı dondurma, `00004` (bit 2) hızlı soğutma, `00008` (bit 3) tatil, `00016` (bit 4) ekonomi. Bitler birleşebilir, ör. `00006` = hızlı soğutma + hızlı dondurma | **çözüldü** -> `Tatil Modu` / `Ekonomi Modu` / `Hızlı Soğutma` / `Hızlı Dondurma` binary sensörleri |
| `RFSSAVE` | Ekran koruyucu - `00000` kapalı, `00001` açık | **çözüldü** -> `Ekran Koruyucu` binary sensörü |
| `RFDCOOL` | Hızlı soğutma | çözülmedi |
| `RFDEFEC` | Buz çözme | çözülmedi |
| `RFCOOER` | Soğutucu | çözülmedi |
| `RFCLOCK` | Çocuk kilidi - `00000` kapalı, `00001` açık | **çözüldü** -> `Çocuk Kilidi` binary sensörü |
| `WIFIRSS` / `WIFISET` | Wi-Fi sinyali / ayarları | ham |

İki mod, buzdolabının kendi göstergesinde ne yazdığını da değiştiriyor ve sıcaklık sensörleri bunu yansıtıyor: **ekonomi** açıkken ikisi de °C yerine `E` gösterir; **tatil** açıkken soğutucu kapatıldığı için `Soğutucu Sıcaklığı` *bilinmiyor* (`--`) olur, dondurucu ise ayarını korur. Çözülmüş sayısal değerler ham `RFTEMSE` sensöründe ve her sıcaklık sensörünün niteliklerinde erişilebilir kalır.

Buzdolabı *kontrolleri* (sıcaklığı ayarlama, eco açma, ...) henüz uygulanmadı - bu yüzden yukarıdaki modlar salt okunur binary sensörlerdir. Komut formatı dokümante değil ve entegrasyon şu an her zaman `device_type: "AC"` gönderiyor. Çözmek için aşağıdaki **Yeni Özellik Keşfetme** iş akışını kullanın; bulduklarınız PR olarak memnuniyetle karşılanır.

## 🧪 Ham API Servisleri

### Cihazın ham durumunu görüntüleme

    vestel_ac.dump_raw_status

### Ham komut gönderme

    vestel_ac.send_raw_code

Örnek:

    action: vestel_ac.send_raw_code
    data:
      code: "ACFANPO00562"

Bu servisler özellikle yeni özelliklerin araştırılması için kullanılabilir.

> ⚠️ Ne yaptığını bilmediğiniz değerleri cihaza göndermeyin.

---

## 🔍 Yeni Özellik Keşfetme

Resmi uygulamadaki bir özelliği araştırmak için:

    dump_raw_status
          ↓
    Uygulamadan özelliği değiştir
          ↓
    dump_raw_status
          ↓
    Değişen alanı bul
          ↓
    Değeri test et
          ↓
    Home Assistant'a ekle

Bu yöntemle dikey kanatçık, salınım, Turbo, Uyku, İyonizer, Tasarruf, Fan modu ve zamanlayıcı gibi birçok özellik keşfedilmiştir.

---

## ❤️ Emeği Geçenler

**Home Assistant entegrasyonu:**  
Mutlu Tekir

**İlk Vestel API araştırması:**  
Sezer İltekin

**Temel proje:**  
https://github.com/iltekin/vestel-ac-remote-control

Bu entegrasyon, ilk API araştırmalarını temel alarak Home Assistant desteği ve APK / gerçek cihaz analizleriyle keşfedilen ek özellikleri bir araya getirir.

---

## ⚠️ Yasal Uyarı

Bu proje resmi değildir ve Vestel ile bağlantılı değildir.

Entegrasyon Vestel'in bulut API'sine bağlıdır. API, kimlik doğrulama sistemi veya servis tarafında yapılacak değişiklikler entegrasyonun çalışmasını engelleyebilir.

Bazı özellikler klima modeli ve firmware sürümüne bağlıdır.

Sorun yaşarsanız:

https://github.com/mutlutekir/Vestel_Klima_AirCon/issues

üzerinden issue açabilirsiniz.

> 🔒 Şifre, access token veya refresh token gibi bilgileri issue içerisinde paylaşmayın.

---

<p align="center">
  🌬️ <strong>Vestel AC + Home Assistant</strong>
  <br>
  <sub>Unofficial Community Integration</sub>
</p>
