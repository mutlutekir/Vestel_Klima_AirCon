Vestel AC — Home Assistant Entegrasyonu (Unofficial)
![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)
![Version](https://img.shields.io/badge/version-0.4.1-blue?style=for-the-badge)
![Maintainer](https://img.shields.io/badge/maintainer-Mutlu%20Tekir-green?style=for-the-badge)
![Unofficial](https://img.shields.io/badge/resmi%20de%C4%9Fil-Vestel%20ile%20ba%C4%9Flant%C4%B1s%C4%B1%20yok-red?style=for-the-badge)

Vestel Doğa/Flora serisi WiFi'li klimaları, resmi Vestel Akıllı Yaşam
uygulamasına hiç ihtiyaç duymadan doğrudan Home Assistant'tan kontrol eden
özel (custom) entegrasyon. Mod, fan hızı, kanatçık (salınım) pozisyonu,
turbo/uyku/iyonizer/tasarruf, otomatik kapatma zamanlayıcısı ve tanı
(hata/uyarı/filtre ömrü) bilgileri dahil — hepsi tek bir `climate` cihazı
altında toplanır.
---
❤️ Emeği Geçenler
Rol	Kişi
İlk Geliştirici	Sezer İltekin — Vestel'in bulut API'sini ilk tersine mühendislikle çözen ve vestel-ac-remote-control Node.js projesini yazan kişi. Bu proje, bu tweet ile başladı.
Home Assistant Entegrasyonu	Mutlu Tekir — Sezer'in bulduğu API'yi Home Assistant'a taşıyan, ek komutları (kanatçık, turbo, uyku, iyonizer, oto-kapatma, tanı sensörleri vb.) APK üzerinden keşfedip ekleyen kişi.
Veri Kaynağı	Vestel Akıllı Yaşam bulut API'si (`sh-native-api.homevsmart.com`) + AWS Cognito kimlik doğrulama.
> *Bu resmi olmayan (unofficial) bir entegrasyondur, Vestel ile hiçbir
> bağlantısı yoktur. Vestel API'yi değiştirirse ya da erişimi kapatırsa
> entegrasyon çalışmayı durdurabilir.*
---
🌐 Kökeni: Vestel Klima Uzaktan Kontrol
Bu entegrasyonun temelindeki API, Vestel "Akıllı Yaşam" mobil
uygulamasının API'si tersine mühendislik yöntemiyle analiz edilerek
geliştirilmiş, kendi sunucunda çalışan bir klima kontrol paneli olan
vestel-ac-remote-control
(Node.js + Express) projesine dayanıyor. Bu Home Assistant entegrasyonu, o
projenin komut mantığını Python'a taşır ve APK'dan keşfedilen ek alanlarla
genişletir.
Orijinal Node.js projesinin özellikleri:
Tam kontrol — açma/kapama, mod (soğutma / ısıtma / nem alma), fan
hızı (oto + 5 kademe), sıcaklık (18–30 °C)
Gerçek zamanlı durum — cihaz durumu açılışta okunur, 30 saniyede bir
güncellenir
Anlık tepki — kontroller hemen yanıt verir, senkronizasyon arka
planda gerçekleşir
Çoklu cihaz — tüm evler ve cihazlar API'den otomatik çekilir, elle
tanımlama gerekmez
Otomasyon — belirli saatte veya oda sıcaklığı eşiğinde otomatik
aç/kapat
Siri kısayolları — her komut için hazır URL ve adım adım kurulum
rehberi
API key koruması — kendin belirlersin, üçüncü taraf hesap gerekmez
---
🌟 Bu Entegrasyonun Özellikleri
🌡️ Tam iklimlendirme kontrolü — Auto / Soğutma / Nem Alma / Sadece
Fan / Isıtma / Kapalı, fan hızı (Auto + 1-5), hedef sıcaklık (18-30°C)
🎯 Kanatçık kontrolü — dikey ve yatay kanatçık için ayrı ayrı
0-6 pozisyon seçici (`select`) + hızlı "Serbest Salınım" / "Salınımı
Durdur" düğmeleri (`button`)
⚡ Turbo, Uyku, İyonizer, Tasarruf Modu — tek dokunuşla açık/kapalı
anahtarlar (`switch`)
⏰ Otomatik kapatma zamanlayıcısı — hedef saat seçici (`time`) +
aktif/pasif anahtarı
🩺 Tanı sensörleri — hata/uyarı kodları, hava kalitesi (VOC/PM),
koku&alerjen filtresi ömrü, parçacık sensörü temizlik ömrü, yazılım
sürümü (cihazınızda yoksa otomatik olarak "kullanılamıyor" görünür,
zararsızdır)
🖼️ Cihaz görseli — marka görseli ilk kurulumda otomatik olarak
`www/` klasörüne kopyalanır, elle hiçbir şey yapmana gerek yok
🔐 Sıfır elle token yönetimi — kurulumda e-posta/şifre gir, arka
planda otomatik giriş yapılır; refresh_token'ı elle bulman gerekmez
(yedek yöntem de mevcut)
🧪 Ham komut servisleri — `send_raw_code` / `dump_raw_status` ile
yeni keşfedilmemiş özellikleri kendi başına deneyebilirsin
---
🚀 Kurulum
Yöntem 1: HACS (Önerilen)
HACS içinde Integrations → sağ üst ⋮ → Custom repositories.
Repo URL'sini ekle, kategori olarak Integration seç.
**"Vestel AC"**yi ara, indir.
Home Assistant'ı yeniden başlat.
Yöntem 2: Manuel
`custom_components/vestel_ac/` klasörünü HA config dizinindeki
`custom_components/` altına kopyala.
Home Assistant'ı yeniden başlat.
⚙️ Yapılandırma
Ayarlar → Cihazlar ve Hizmetler → + Entegrasyon Ekle → "Vestel AC".
"Kullanıcı adı / şifre (otomatik)" seçeneğini seç, Vestel Akıllı
Yaşam hesap bilgilerini gir. Home Assistant arka planda giriş
isteklerini gönderip token'ı otomatik alır — kopyala/yapıştır yok,
telefon dışında bir cihaza gerek yok.
Otomatik giriş çalışmazsa (Vestel sayfa yapısını değiştirirse), aynı
menüden **"Refresh token yapıştır (yedek yöntem)"**ni kullanabilirsin.
🖼️ Cihaz görseli
Vestel'in logosunu telif nedeniyle kullanamıyorum; bunun yerine paket
içinde jenerik bir klima çizimi + "VESTEL KLIMA AirCon" yazılı bir görsel
var (`custom_components/vestel_ac/assets/vestel_ac.png`).
Elle bir şey yapmana gerek yok — entegrasyon, ilk kurulumda bu dosyayı
otomatik olarak HA config dizinindeki `www/vestel_ac/vestel_ac.png`
konumuna kopyalar (yoksa `www/vestel_ac/` klasörünü kendisi oluşturur).
Bu adım, custom_component'lerin kurulumdan sonra zaten gerektirdiği tek
"Home Assistant'ı yeniden başlat" adımıyla aynı anda gerçekleşir.
Kendi görselini/fotoğrafını koymak istersen: `www/vestel_ac/vestel_ac.png`
dosyasının üzerine kendi dosyanı aynı isimle yaz — entegrasyon, dosya zaten
varsa üzerine yazmaz, senin koyduğun kalır.
---
🎛️ Deşifre Edilen Komutlar (APK + gerçek cihaz verisiyle doğrulandı)
> APK dosyası (`Vestel Akıllı Yaşam`) incelenerek potansiyel komut/alan
> isimleri ortaya çıkarılmış, bir kısmı da gerçek bir cihazdan alınan
> canlı durum verisiyle bit-bit çapraz doğrulanmıştır. Aşağıda hangisinin
> **doğrulanmış**, hangisinin **sadece APK spesifikasyonundan** geldiği
> ayrı ayrı belirtiliyor.
✅ Doğrulanmış (gerçek cihaz verisiyle test edildi)
ACCMODE / ACGENSI — mod + fan hızı: `ACGENSI = ACCMODE + FanSpeed × 8`
ACCMODE	Anlamı
0	Auto
1	Soğutma
2	Nem Alma
3	Sadece Fan
4	Isıtma
5	Kapalı
ACFANPO — paketlenmiş anahtarlar + kanatçık pozisyonu (tek sayı, bit bit):
Bit(ler)	Alan	Değer
0	Turbo	+1
1-3	Dikey Kanatçık	0=durdur, 1-5=kademe, 6=salınım
4-6	Yatay Kanatçık	aynı 0-6 (simetriden çıkarıldı, doğrulanmadı)
7	Uyku Modu	+128
8	İyonizer	+256

9	Tasarruf Modu	+512
ACOFFTV — otomatik kapatma hedef saati: `değer = (dakika << 5) \| saat`,
`2047` = devre dışı. Örnek: 14:18 → `00590` (doğrulandı).
📖 Sadece APK spesifikasyonundan (bu cihazda henüz görülmedi/test edilmedi)
Alan	Anlamı
`ACERROR`	16 bitlik hata bayrakları (sensör arızaları, gaz kaçağı, iletişim hatası, vb.)
`ACERRTW`	UVC hatası (bit0), Parçacık Sensörü hatası (bit1)
`ACWARNG`	0=Uyarı yok, 1=UVC ömrü doldu
`ACPOLVC`	Hava kalitesi (VOC): 0=İyi, 1=Orta, 2=Kötü
`ACPOLPM`	Hava kalitesi (Partikül): 0=Temiz, 1=Orta, 2=Kirli
`ACOAFLP` / `ACPSCLP`	Koku&Alerjen filtresi / Parçacık sensörü temizlik ömrü (%)
`ACSAFRS`	Sayaç sıfırlama: 1=filtre, 10=parçacık sensörü
`ACRGBON/ACRGBST/ACRGBBR`	Ortam ışığı aç/kapa, ton (0-3), parlaklık (1-3)
`ACVERSI`	Yazılım adı+sürümü: alt bayt=isim (3=Meltem, 4=Yağmur), üst bayt=sürüm
`ACTEMOT` (oto-başlatma modunda)	Hedef sıcaklıkla aynı alanı paylaşıyor; saat=bit4-8, dakika=bit9-14 — düşük 4 bitte açıklanamayan bir işaretleyici olduğu için yazma desteği eklenmedi (yanlış giderse sıcaklık ayarını bozma riski var)
Bu alanlardan bazıları (`ACPOLVC`, `ACRGBON` gibi) bu spesifik cihazın
durum çıktısında hiç görünmüyor — muhtemelen bu donanım özelliği (parçacık
sensörü, RGB ışık) bu modelde yok. İlgili entity'ler bu durumda sadece
"kullanılamıyor" gösterir, zararsızdır.
---
🧪 Ham komut gönderme (yeni özellik keşfetmek için)
HA'nın Geliştirici Araçları → Eylemler kısmından çağrılabilir:
`vestel_ac.dump_raw_status` — cihazın o anki tüm ham alanlarını bildirim
olarak gösterir.
`vestel_ac.send_raw_code` — elle yazdığın bir kodu (`{"code": "ACFANPO00562"}` gibi) doğrudan cihaza gönderir.
Akış: resmi uygulamada bir düğmeye basmadan önce/sonra `dump_raw_status`
çalıştır, hangi alanın değiştiğini gör, sonra `send_raw_code` ile aynı
değeri kendin göndermeyi dene.
---
⚠️ Bilinen Sınırlamalar
Otomatik e-posta/şifre girişi, Vestel'in Cognito Hosted UI sayfasının
bugünkü HTML yapısına dayanır; Vestel bunu değiştirirse (captcha/2FA
eklerse) "refresh_token yapıştır" yedek yöntemi kullanılmalı.
Yatay kanatçık kontrolü dikey ile simetriden çıkarıldı, ayrıca test
edilmedi.
Otomatik başlatma (auto-start) zamanlayıcısı, hedef sıcaklıkla aynı
alanı paylaştığı ve tam çözülmediği için eklenmedi.
Refresh token geçersiz olursa entegrasyonu kaldırıp yeniden kurman
gerekir.
---
