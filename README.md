<h1 align="center">
  🌬️ Vestel AC
</h1>

<h3 align="center">
  Home Assistant için gelişmiş Vestel Klima entegrasyonu
</h3>

<p align="center">
  Vestel Doğa / Flora serisi Wi-Fi'li klimaları doğrudan Home Assistant üzerinden kontrol edin.
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=mutlutekir&repository=Vestel_Klima_AirCon&category=integration">
    <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="HACS ile yükle">
  </a>
  &nbsp;&nbsp;
  <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=vestel_ac">
    <img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Home Assistant'a ekle">
  </a>
</p>

<p align="center">
  <a href="https://github.com/mutlutekir/Vestel_Klima_AirCon/releases">
    <img src="https://img.shields.io/github/v/release/mutlutekir/Vestel_Klima_AirCon?style=for-the-badge" alt="Latest Release">
  </a>
  <a href="https://github.com/mutlutekir/Vestel_Klima_AirCon/stargazers">
    <img src="https://img.shields.io/github/stars/mutlutekir/Vestel_Klima_AirCon?style=for-the-badge" alt="GitHub Stars">
  </a>
  <a href="https://github.com/hacs/integration">
    <img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge" alt="HACS">
  </a>
</p>

---

# 🌬️ Vestel AC — Home Assistant Entegrasyonu

Vestel Doğa / Flora serisi Wi-Fi'li klimaları, resmi **Vestel Akıllı Yaşam** uygulamasına ihtiyaç duymadan doğrudan Home Assistant üzerinden kontrol etmenizi sağlayan özel (**custom**) entegrasyondur.

Mod, fan hızı, sıcaklık, dikey/yatay kanatçık, salınım, turbo, uyku, iyonizer, tasarruf modu, otomatik kapatma zamanlayıcısı ve tanı bilgileri tek bir Home Assistant entegrasyonu altında toplanır.

> ⚠️ **Bu resmi bir Vestel entegrasyonu değildir.**
>
> Vestel ile herhangi bir bağlantısı veya resmi desteği yoktur.
> Vestel API'yi değiştirirse veya erişimi kapatırsa entegrasyon çalışmayı durdurabilir.

---

# ✨ Özellikler

| Özellik | Durum |
|---|:---:|
| 🌡️ Sıcaklık kontrolü | ✅ |
| ❄️ Soğutma | ✅ |
| ☀️ Isıtma | ✅ |
| 💧 Nem alma | ✅ |
| 🌀 Sadece fan | ✅ |
| 🤖 Otomatik mod | ✅ |
| 🌀 Fan Auto + 1-5 | ✅ |
| 🎯 Dikey kanatçık | ✅ |
| ↔️ Yatay kanatçık | ⚠️ Modele bağlı |
| 🔄 Dikey salınım | ✅ |
| ⚡ Turbo | ✅ |
| 🌙 Uyku | ✅ |
| 🍃 Tasarruf / Eco | ✅ |
| ✨ İyonizer | ✅ |
| ⏰ Otomatik kapatma | ✅ |
| 🩺 Hata / uyarı bilgileri | ✅ |
| 🌫️ VOC / hava kalitesi | ⚠️ Donanıma bağlı |
| 🫧 PM / partikül bilgisi | ⚠️ Donanıma bağlı |
| 🧹 Filtre ömrü | ⚠️ Donanıma bağlı |
| 🧪 Ham API komutları | ✅ |

---

# 🛠️ Desteklenen Klima Kontrolleri

## 🌡️ İklimlendirme

- Auto
- Soğutma
- Isıtma
- Nem Alma
- Sadece Fan
- Kapalı
- 18-30 °C hedef sıcaklık
- Fan Auto
- Fan 1-5

## 🎯 Kanatçık Kontrolü

- Dikey kanatçık 1-5
- Dikey serbest salınım
- Dikey salınımı durdur
- Yatay kanatçık desteği
- Yatay salınım desteği modele bağlıdır

## ⚡ Özel Modlar

- Turbo
- Uyku
- İyonizer
- Tasarruf / Eco

## ⏰ Zamanlayıcı

- Otomatik kapatma
- Saat/dakika tabanlı kapanma

---

# 🚀 Kurulum

## 🛒 Yöntem 1 — HACS

**Önerilen kurulum yöntemidir.**

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=mutlutekir&repository=Vestel_Klima_AirCon&category=integration">
    <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Vestel AC'yi HACS ile yükle">
  </a>
</p>

### HACS ile kurulum

1. Home Assistant'ta **HACS**'ı açın.
2. **Integrations** bölümüne girin.
3. Sağ üstteki **⋮** menüsüne tıklayın.
4. **Custom repositories** seçeneğini açın.
5. Aşağıdaki repository adresini girin:

    https://github.com/mutlutekir/Vestel_Klima_AirCon

6. Kategori olarak **Integration** seçin.
7. **Add** butonuna basın.
8. **Vestel AC** entegrasyonunu bulun.
9. **Download** seçeneğine basın.
10. Home Assistant'ı yeniden başlatın.

---

# 📦 Yöntem 2 — Manuel Kurulum

Repository'nin en son sürümünü indirin:

https://github.com/mutlutekir/Vestel_Klima_AirCon/releases

Aşağıdaki klasör yapısının Home Assistant içerisinde bulunması gerekir:

    /config/
    └── custom_components/
        └── vestel_ac/
            ├── __init__.py
            ├── climate.py
            ├── sensor.py
            ├── select.py
            ├── switch.py
            ├── button.py
            ├── time.py
            ├── config_flow.py
            ├── manifest.json
            └── ...

Ardından Home Assistant'ı yeniden başlatın.

---

# ⚙️ Entegrasyonu Ekleme

<p align="center">
  <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=vestel_ac">
    <img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Vestel AC'yi Home Assistant'a ekle">
  </a>
</p>

Manuel olarak eklemek için:

    Ayarlar
       ↓
    Cihazlar ve Hizmetler
       ↓
    + Entegrasyon Ekle
       ↓
    Vestel AC

---

# 🔐 Kimlik Doğrulama

Vestel AC entegrasyonu iki farklı giriş yöntemi destekler.

| Yöntem | Açıklama | Öneri |
|---|---|:---:|
| 👤 Kullanıcı adı / Şifre | Vestel Akıllı Yaşam hesabıyla otomatik giriş | ⭐⭐⭐ |
| 🔑 Refresh Token | Yedek kimlik doğrulama yöntemi | ⭐ |

## 👤 Kullanıcı adı / Şifre

Kurulum ekranında:

    Kullanıcı adı / şifre (otomatik)

seçeneğini seçin.

Vestel Akıllı Yaşam hesabınızın:

    E-posta
    Şifre

bilgilerini girin.

Entegrasyon arka planda gerekli kimlik doğrulama işlemlerini yaparak klima cihazlarını keşfeder.

---

# 🔑 Refresh Token — Yedek Yöntem

Otomatik giriş Vestel tarafındaki giriş ekranı değişiklikleri nedeniyle çalışmazsa refresh token yöntemi kullanılabilir.

Kurulum ekranından:

    Refresh token yapıştır

seçeneğini kullanabilirsiniz.

> 💡 Bu yöntem özellikle Vestel'in Cognito Hosted UI veya giriş akışında değişiklik yapması durumunda yedek olarak bulunmaktadır.

---

# 🧭 Kurulum Akışı

    🏠 Home Assistant
             │
             ▼
       ┌───────────────┐
       │  Kurulum      │
       └───────┬───────┘
               │
       ┌───────┴────────┐
       ▼                ▼
     🛒 HACS          📦 Manuel
       │                │
       └───────┬────────┘
               ▼
        🔄 Home Assistant
           Restart
               │
               ▼
        ⚙️ Vestel AC
        Entegrasyonunu Ekle
               │
        ┌──────┴──────┐
        ▼             ▼
    👤 E-posta      🔑 Refresh
       + Şifre        Token
        │             │
        └──────┬──────┘
               ▼
       ☁️ Vestel Cloud API
               │
               ▼
          🔎 Cihaz Keşfi
               │
               ▼
          🌬️ Vestel AC

---

# 🏠 Home Assistant Entity'leri

Kurulum tamamlandıktan sonra klima Home Assistant içerisinde bir `climate` entity olarak görünür.

Örneğin:

    climate.klima

Ek özellikler için aşağıdaki entity'ler kullanılabilir:

    select.salon_klima_dikey_kanatcik

    button.salon_klima_dikey_kanatcik_salinimi_durdur
    button.salon_klima_dikey_kanatcik_serbest_salinim

    switch.salon_klima_iyonizer
    switch.salon_klima_tasarruf_modu
    switch.salon_klima_turbo
    switch.salon_klima_uyku_modu

Entity isimleri Home Assistant tarafından cihaz adına göre değişebilir.

---

# 🎯 Dikey Kanatçık

Gerçek cihaz üzerinde yapılan testlerde dikey kanatçık için aşağıdaki değerler doğrulanmıştır:

| Pozisyon | ACFANPO |
|---|---:|
| ⬆️ En üst | `00050` |
| ↗️ Üstten 2. kademe | `00052` |
| ↗️ Üstten 3. kademe | `00054` |
| ↘️ Üstten 4. kademe | `00056` |
| ⬇️ En alt | `00058` |
| 🔄 Serbest salınım | `00060` |
| ⏹️ Salınımı durdur / sabitle | `00048` |

Bu değerler gerçek cihazdan alınan durum değişiklikleriyle doğrulanmıştır.

---

# 🌀 ACCMODE — Klima Modu

`ACCMODE` klimanın çalışma modunu belirtir.

| Değer | Mod |
|---:|---|
| `0` | Auto |
| `1` | Soğutma |
| `2` | Nem Alma |
| `3` | Sadece Fan |
| `4` | Isıtma |
| `5` | Kapalı |

---

# 🌀 ACGENSI — Mod + Fan Hızı

Gerçek cihaz üzerinden doğrulanan yapı:

    ACGENSI = ACCMODE + FanSpeed × 8

Örneğin:

    ACCMODE = 1
    FanSpeed = 1

    ACGENSI = 1 + (1 × 8)
            = 9

Fan hızları cihaz tarafından bu alan üzerinden kodlanabilir.

---

# 🎯 ACFANPO — Kanatçık ve Özel Modlar

`ACFANPO`, birden fazla özelliği tek bir sayısal değer içerisinde bit alanları kullanarak taşır.

| Bit | Özellik | Değer |
|---:|---|---|
| 0 | Turbo | +1 |
| 1-3 | Dikey kanatçık | 0-6 |
| 4-6 | Yatay kanatçık | 0-6 |
| 7 | Uyku | +128 |
| 8 | İyonizer | +256 |
| 9 | Tasarruf | +512 |

Dikey kanatçık:

    0 = Durdur
    1 = Kademe 1
    2 = Kademe 2
    3 = Kademe 3
    4 = Kademe 4
    5 = Kademe 5
    6 = Salınım

---

# ⚡ Gerçek Cihazda Doğrulanan Özel Modlar

| Özellik | Alan | Değer |
|---|---|---:|
| Normal | ACFANPO | `00050` |
| Turbo | ACGENSI | `00025` |
| Uyku | ACFANPO | `00178` |
| İyonizer | ACFANPO | `00306` |
| Tasarruf | ACFANPO | `00562` |
| Dikey Swing | ACFANPO | `00060` |

---

# 🌙 Özel Modların Bit Karşılıkları

`ACFANPO` içerisinde:

    Turbo     = +1
    Uyku      = +128
    İyonizer  = +256
    Tasarruf  = +512

Örneğin:

    Normal:
    00050

    Tasarruf:
    00050 + 512
    = 00562

İyonizer:

    00050 + 256
    = 00306

Uyku:

    00050 + 128
    = 00178

Bu değerler gerçek cihaz üzerinden gözlemlenmiştir.

---

# 🌀 Fan Modu

Bazı Vestel modellerinde Home Assistant'ın standart `climate` entity'sinde fan-only modu görünmeyebilir.

Bu entegrasyonda Vestel API'sinin gerçek cihaz davranışı kullanılarak:

    ACCMODE = 3

değeri **Sadece Fan** modu olarak desteklenmektedir.

Gerçek cihazdan örnek:

    ACCMODE = 00003
    ACGENSI = 00011

---

# ⏰ ACOFFTV — Otomatik Kapatma

Otomatik kapanma zamanı:

    ACOFFTV = (dakika << 5) | saat

Devre dışı değeri:

    2047

Örneğin:

    14:18

için:

    ACOFFTV = 00590

değeri gözlemlenmiştir.

---

# ⏰ Otomatik Başlatma

Otomatik başlatma sırasında cihaz durumunda `ACTEMOT` alanının değiştiği gözlemlenmiştir.

Örneğin:

    ACTEMOT = 09994

Ancak `ACTEMOT` alanının hedef sıcaklık ile aynı alanı paylaşması ve düşük bitlerde henüz tam olarak açıklanamayan bir işaretleyici bulunması nedeniyle otomatik başlatma için yazma desteği şu aşamada eklenmemiştir.

Yanlış değer gönderilmesi hedef sıcaklık ayarını değiştirebilir.

---

# 🩺 Diagnostik Alanlar

APK analizi ve API araştırması sırasında aşağıdaki alanlar tespit edilmiştir.

| Alan | Açıklama |
|---|---|
| `ACERROR` | Hata bilgileri |
| `ACERRTW` | UVC / partikül sensörü hata bilgileri |
| `ACWARNG` | Uyarı bilgileri |
| `ACPOLVC` | VOC hava kalitesi |
| `ACPOLPM` | Partikül / PM hava kalitesi |
| `ACOAFLP` | Koku & alerjen filtre ömrü |
| `ACPSCLP` | Partikül sensörü temizlik ömrü |
| `ACSAFRS` | Filtre / sensör sayaç sıfırlama |
| `ACVERSI` | Yazılım sürümü |

---

# 🌫️ Hava Kalitesi

Bazı Vestel klima modellerinde hava kalitesi sensörleri bulunabilir.

APK içerisinde tespit edilen alanlar:

    ACPOLVC
    ACPOLPM

### VOC

    ACPOLVC

değerleri:

| Değer | Anlam |
|---:|---|
| `0` | İyi |
| `1` | Orta |
| `2` | Kötü |

### Partikül / PM

    ACPOLPM

değerleri:

| Değer | Anlam |
|---:|---|
| `0` | Temiz |
| `1` | Orta |
| `2` | Kirli |

> ⚠️ Bu alanların cihaz tarafından gönderilmesi donanıma bağlıdır.

---

# 🧹 Filtre ve Sensör Ömrü

APK'da aşağıdaki alanlar tespit edilmiştir:

    ACOAFLP
    ACPSCLP

Bunlar sırasıyla:

    Koku & Alerjen filtresi
    Partikül sensörü

ile ilişkilidir.

Sayaç sıfırlama alanı:

    ACSAFRS

olarak tespit edilmiştir.

Bilinen değerler:

    1  = Filtre
    10 = Partikül sensörü

---

# 💡 RGB / Ortam Işığı

APK spesifikasyonunda aşağıdaki alanlar tespit edilmiştir:

    ACRGBON
    ACRGBST
    ACRGBBR

Muhtemel anlamları:

| Alan | Anlam |
|---|---|
| `ACRGBON` | Ortam ışığı aç/kapa |
| `ACRGBST` | Işık tonu |
| `ACRGBBR` | Parlaklık |

Ancak bu özellik mevcut klima cihazında doğrulanmamıştır.

---

# 🧪 ACVERSI — Yazılım Sürümü

`ACVERSI` cihaz yazılım adı ve sürüm bilgilerini taşır.

APK araştırmasına göre:

    Alt bayt = Yazılım adı
    Üst bayt = Sürüm

Bilinen isim kodları:

    3 = Meltem
    4 = Yağmur

Örneğin gerçek cihazda:

    ACVERSI = 23043

değeri gözlemlenmiştir.

---

# 🔬 Ham Durum Görüntüleme

Yeni özellikleri araştırmak için:

    vestel_ac.dump_raw_status

servisi kullanılabilir.

Bu servis cihazın API'den döndürdüğü ham alanları görüntülemek için kullanılır.

Önerilen keşif yöntemi:

    1. dump_raw_status çalıştır
    2. Vestel Akıllı Yaşam uygulamasını aç
    3. Bir özelliği değiştir
    4. dump_raw_status tekrar çalıştır
    5. Değişen alanları karşılaştır
    6. Alanın ne yaptığını belirle
    7. Gerekirse send_raw_code ile test et

---

# 🧪 Ham Komut Gönderme

Servis:

    vestel_ac.send_raw_code

Örneğin:

    action: vestel_ac.send_raw_code
    data:
      code: "ACFANPO00562"

Bu örnek `ACFANPO00562` değerini cihaza göndermeyi dener.

> ⚠️ Ham komutları yalnızca ne yaptığını bildiğiniz değerlerle kullanın.

Yanlış değerler cihaz davranışını değiştirebilir.

---

# 🔎 APK ile Özellik Keşfi

Bu entegrasyon geliştirilirken Vestel Akıllı Yaşam APK'sı içerisindeki alan ve komut isimleri incelenmiş, daha sonra gerçek cihazdan alınan durum bilgileriyle karşılaştırılmıştır.

Örneğin:

    Vestel Akıllı Yaşam
             │
             ▼
        APK analizi
             │
             ▼
       Olası alanlar
             │
             ▼
      Gerçek cihaz testi
             │
             ▼
       Raw status karşılaştırması
             │
             ▼
       Bit / değer analizi
             │
             ▼
       Home Assistant entity
             │
             ▼
        Kullanılabilir özellik

Bu yöntem sayesinde resmi Home Assistant entegrasyonlarında bulunmayan birçok klima kontrolü keşfedilmiştir.

---

# 🌐 API Mimarisi

Entegrasyonun temel iletişim yapısı:

    Vestel Akıllı Yaşam
             │
             ▼
    sh-native-api.homevsmart.com
             │
             ▼
        AWS Cognito
             │
             ▼
       Vestel Cloud API
             │
             ▼
       Vestel AC Integration
             │
             ▼
        Home Assistant
             │
             ▼
          Klima

---

# 🌐 Projenin Kökeni

Bu entegrasyonun temelindeki API, Vestel **Akıllı Yaşam** mobil uygulamasının API'sinin tersine mühendislik yöntemiyle incelenmesi sonucu ortaya çıkarılmıştır.

İlk API araştırmaları ve temel komut mantığı:

**Sezer İltekin**

tarafından geliştirilen:

https://github.com/iltekin/vestel-ac-remote-control

projesine dayanmaktadır.

Bu Home Assistant entegrasyonu, API mantığını Python/Home Assistant ortamına taşır ve APK ile gerçek cihaz üzerinde yapılan araştırmalarla ek özellikleri destekler.

---

# ❤️ Emeği Geçenler

| Rol | Kişi |
|---|---|
| İlk API araştırması | [Sezer İltekin](https://x.com/sezeriltekin) |
| İlk Node.js uygulaması | [vestel-ac-remote-control](https://github.com/iltekin/vestel-ac-remote-control) |
| Home Assistant entegrasyonu | **Mutlu Tekir** |
| Ek komutların keşfi | **Mutlu Tekir** |
| APK analizi | **Mutlu Tekir** |
| Gerçek cihaz doğrulaması | **Mutlu Tekir** |

---

# 📚 Kaynaklar

### Vestel AC Home Assistant

https://github.com/mutlutekir/Vestel_Klima_AirCon

### İlk API araştırması

https://github.com/iltekin/vestel-ac-remote-control

### Home Assistant

https://www.home-assistant.io/

### HACS

https://www.hacs.xyz/

---

# ⚠️ Bilinen Sınırlamalar

- Bu entegrasyon resmi Vestel entegrasyonu değildir.
- Vestel API'si değişirse entegrasyon çalışmayabilir.
- Bazı özellikler yalnızca belirli klima modellerinde bulunur.
- Hava kalitesi / PM / VOC sensörleri donanıma bağlıdır.
- Filtre ömrü bilgileri donanıma ve firmware'e bağlıdır.
- Yatay kanatçık desteği her cihazda doğrulanmamıştır.
- Bazı APK alanları teorik olarak tanımlanmış ancak her cihazda test edilmemiştir.
- RGB / ortam ışığı alanları her cihazda bulunmayabilir.
- Refresh token geçersiz hale gelirse yeniden kimlik doğrulama gerekebilir.

---

# 🐛 Hata Bildirme

Bir problem yaşarsanız GitHub Issues bölümünden bildirebilirsiniz:

https://github.com/mutlutekir/Vestel_Klima_AirCon/issues

Hata bildirirken mümkünse aşağıdaki bilgileri ekleyin:

    Vestel klima modeli:
    Home Assistant sürümü:
    Vestel AC entegrasyon sürümü:
    Hata mesajı:
    dump_raw_status çıktısı:

> 🔒 Şifre, refresh token, access token veya kişisel hesap bilgilerinizi kesinlikle paylaşmayın.

---

# ⭐ Destek

Bu proje işinize yaradıysa GitHub üzerinde ⭐ bırakabilirsiniz.

https://github.com/mutlutekir/Vestel_Klima_AirCon

---

<p align="center">
  <strong>🌬️ Vestel AC + Home Assistant</strong>
  <br>
  <sub>Unofficial • Community Project • Reverse Engineered API</sub>
</p>
