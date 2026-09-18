# Trelleborg Avfall

Home Assistant-integration som hämtar dina tömningsdagar från
[Kretslopp och vatten, Trelleborgs kommun](https://www.trelleborg.se/bygga-bo-miljo/avfall-och-atervinning/).

**Fristående** – den har inget med `waste_collection_schedule` att göra och kan
köras samtidigt som, eller i stället för, den.

## Vad du får

| Entitet | Vad den gör |
|---|---|
| `sensor.*_next_pickup` | Datum för nästa tömning (alla kommande i attributet `upcoming`) |
| `sensor.*_days_until_pickup` | Antal dagar kvar till nästa tömning |
| `sensor.*_next_waste_type` | Vilken tunna som är näst på tur, t.ex. `Fyrfack 2` |
| `sensor.*_fyrfack_1`, `*_fyrfack_2`, `*_restavfall` | En sensor per kärl med kärlets nästa tömning |
| `sensor.*_fyrfack_1_days_until`, ... | Antal dagar kvar till just det kärlets tömning |
| `binary_sensor.*_pickup_today` | På hela tömningsdagen |
| `binary_sensor.*_pickup_tomorrow` | På hela dagen innan |
| `calendar.*_pickups` | Alla tömningar som heldagshändelser |

En sensor per kärl skapas automatiskt utifrån dina abonnemang, så antalet
varierar beroende på vad du har.

> Entitets-ID:na följer integrationens namn. Kör du Home Assistant på svenska blir
de i stället `sensor.*_nasta_tomning`, `binary_sensor.*_tomning_imorgon` och så
vidare – kolla under *Utvecklarverktyg → Tillstånd*.

De två binära sensorerna slår om strax efter midnatt, så automationer med
`to: "on"` körs rätt dag.

### Attribut att bygga automationer på

**`binary_sensor.*_pickup_today` / `*_pickup_tomorrow`**

| Attribut | Exempel |
|---|---|
| `date` | `2026-09-29` |
| `waste_types` | `["Fyrfack 1", "Restavfall"]` |
| `bins` | `["370 l Fyrfackskärl", "190 l Kärl"]` |
| `bin_descriptions` | `["Kärl, 370 L fyrfack. Kärl 1. Var 14:e dag", ...]` |

**`sensor.*_next_pickup`**

| Attribut | Exempel |
|---|---|
| `waste_type` | `Fyrfack 1` |
| `bin` | `370 l Fyrfackskärl` |
| `bin_description` | `Kärl, 370 L fyrfack. Kärl 1. Var 14:e dag` |
| `days_until` | `12` |
| `upcoming` | lista med `date`, `waste_type`, `bin`, `bin_description`, `days_until` |

### Var ser jag allt?

Det mesta finns som egna entiteter (tabellen ovan). Attributen är kvar för
avancerade mallar och innehåller hela den kommande listan.

**Alla attribut:** *Utvecklarverktyg → Tillstånd* (Developer Tools → States), sök på
`trelleborg_avfall` och klicka på entiteten. Där finns `upcoming` med hela schemat.
Samma lista visas om du klickar på entiteten i gränssnittet – attributen ligger
längst ned i panelen.

**Alla datum i kalenderform:** lägg till ett *Kalenderkort* på en dashboard och välj
**Trelleborg Avfall**. Kalenderns status (*Off*) betyder bara att ingen tömning
pågår just nu – händelserna ligger kvar.

**Egen lista på dashboarden** (Markdown-kort):

```yaml
type: markdown
title: Kommande tömningar
content: >
  {% set u = state_attr('sensor.trelleborg_avfall_next_pickup', 'upcoming') or [] %}
  {% for p in u[:6] %}
  **{{ p.date }}** – {{ p.waste_type }}, {{ p.bin }} (om {{ p.days_until }} dagar)
  {% endfor %}
```

**Portalens egen beskrivning av tunnan:** sensorns attribut `bin_description`, till
exempel `Kärl, 370 L fyrfack. Kärl 1. Var 14:e dag`.

> Entitets-ID:na beror på vad enheten heter i din installation. Kontrollera dem under
> *Utvecklarverktyg → Tillstånd* och byt ut vid behov.

## Installation

### Via HACS

1. HACS → tre prickar uppe till höger → **Anpassade repositories**
2. Klistra in `https://github.com/nikeng-forenade/trelleborg_avfall`
   och välj kategori **Integration**
3. Sök upp **Trelleborg Avfall** i HACS och klicka **Ladda ned**
4. Starta om Home Assistant

### Manuellt

Kopiera mappen `custom_components/trelleborg_avfall` till din HA-konfiguration:

```
/config/custom_components/trelleborg_avfall/
```

Starta om Home Assistant.

## Konfiguration

**Inställningar → Enheter och tjänster → Lägg till integration → Trelleborg Avfall**

| Fält | Beskrivning |
|---|---|
| Kundnummer | Står på din faktura från Kretslopp och vatten |
| Personnummer | 12 siffror (ÅÅÅÅMMDDXXXX), eller organisationsnummer med inledande 00 |
| Adress | Valfritt – behövs bara om kontot har fler än en fastighet |

> **OBS:** Portalen låser formulärinloggningen efter **tre felaktiga försök**.
> Kontrollera uppgifterna noga. Har du bara BankID kan kommunens kontaktcenter
> (0410-73 30 00) hjälpa dig att aktivera inloggningen utan BankID.

### Uppdateringsintervall

**Integrationskortet → Konfigurera** låter dig ställa hur ofta nya tider hämtas –
i **dagar** (1–30, standard 1).

Kommunen publicerar hela säsongen på en gång (hämtschemat är en PDF med alla
datum), så det finns ingen anledning att fråga portalen ofta. Ett längre intervall
belastar deras tjänst mindre, och eftersom fastighets-ID:t sparas kräver varje
hämtning ingen inloggning – bara två anrop.

När det kända schemat börjar ta slut (21 dagar kvar) hämtas det automatiskt en
gång om dagen igen, så nästa säsong inte missas.

## Automationer

Vill du ha med **vilken tunna** det gäller i meddelandet använder du `bins` i
stället för `waste_types` – samma uppbyggnad, se attributtabellen ovan.

### Påminnelse dagen innan

```yaml
automation:
  - alias: Påminnelse kvällen innan tömning
    triggers:
      - trigger: state
        entity_id: binary_sensor.trelleborg_avfall_pickup_tomorrow
        to: "on"
    actions:
      - action: notify.mobile_app_din_telefon
        data:
          title: "Tömning imorgon"
          message: >-
            {{ state_attr('binary_sensor.trelleborg_avfall_pickup_tomorrow',
               'waste_types') | join(', ') }}
```

### Åtgärd på tömningsdagen

```yaml
automation:
  - alias: Ställ ut kärlet
    triggers:
      - trigger: state
        entity_id: binary_sensor.trelleborg_avfall_pickup_today
        to: "on"
    actions:
      - action: notify.mobile_app_din_telefon
        data:
          message: >-
            Idag töms: {{ state_attr('binary_sensor.trelleborg_avfall_pickup_today',
            'waste_types') | join(', ') }}
```

### Bara en viss tunna

Enklast är att använda kärlets egen sensor. Den här körs dagen innan Fyrfack 2
töms:

```yaml
automation:
  - alias: Påminnelse Fyrfack 2
    triggers:
      - trigger: numeric_state
        entity_id: sensor.trelleborg_avfall_fyrfack_2_days_until
        below: 2
    actions:
      - action: notify.mobile_app_din_telefon
        data:
          message: "Fyrfack 2 töms imorgon"
```

Vill du i stället filtrera på avfallstyp kan du använda attributet `waste_types`:

```yaml
    conditions:
      - condition: template
        value_template: >-
          {{ 'Trädgårdsavfall' in state_attr(
             'binary_sensor.trelleborg_avfall_pickup_tomorrow', 'waste_types') }}
```

## Blueprints (färdiga automationer)

| Blueprint | Vad den gör |
|---|---|
| **Påminnelse före tömning** | Skickar ett meddelande när det är dags för tömning. Välj sensorn *Tömning idag* eller *Tömning imorgon* och en väntetid – 18 timmar ger påminnelsen kl 18 dagen innan. |
| **Översikt över kommande tömningar** | Skickar hela listan, till exempel varje söndag kl 18. Antal dagar framåt ställs in. |

Båda blueprintarna har fält för rubrik och meddelandetext, så du kan ändra
ordalydelsen direkt i formuläret utan att röra YAML.

### Så här får du in blueprinten

**1. Importera.** Enklast är knapparna här – de öppnar din egen Home Assistant
och frågar om du vill importera:

[![Importera påminnelsen](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fnikeng-forenade%2Ftrelleborg_avfall%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Ftrelleborg_avfall%2Fpaminnelse.yaml)

[![Importera översikten](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fnikeng-forenade%2Ftrelleborg_avfall%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Ftrelleborg_avfall%2Fveckooversikt.yaml)

Fungerar inte knapparna? Gör så här i stället:

* **Klistra in adressen själv:** *Inställningar → Automationer och scener →
  Blueprintar → Importera blueprint* och klistra in

  ```
  https://github.com/nikeng-forenade/trelleborg_avfall/blob/main/blueprints/automation/trelleborg_avfall/paminnelse.yaml
  ```

  (byt ut `paminnelse` mot `veckooversikt` för den andra).
* **Kopiera filen:** lägg `paminnelse.yaml` i
  `/config/blueprints/automation/trelleborg_avfall/` (skapa mappen först) och
  starta om Home Assistant.

**2. Skapa automationen.** *Inställningar → Automationer och scener → Skapa
automation →* välj **Trelleborg Avfall – påminnelse före tömning**. Fyll i
formuläret och spara.

**3. Testa.** Öppna automationen och kör den manuellt (*tre prickar → Kör*).
Blueprinten läser av sensorn du valde, så du behöver inte vänta på midnatt –
meddelandet skickas direkt. Standardtexten ser ut så här:

```text
Tömning imorgon
Fyrfack 2 töms imorgon (2026-09-24). Kärl: 370 l Fyrfackskärl.
```

Vill du uppdatera en blueprint senare importerar du bara samma adress igen –
Home Assistant frågar om den ska skrivas över.

### Testa hela kedjan

Körningen ovan testar texten och åtgärden, men inte utlösaren. Vill du se att
även triggern funkar:

1. Sätt **Väntetid** till `0` medan du testar (annars dröjer det 18 timmar).
2. *Utvecklarverktyg → Tillstånd*, leta upp `binary_sensor.*_pickup_today`,
   klicka på kugghjulet, skriv `on` i *Tillstånd* och tryck **Ange tillstånd**.
3. Automationen körs nu – titta i *Spårning* (Logbook/Spårning på
   automationens sida) för att se stegen och vad mallarna gav.
4. Sätt tillbaka väntetiden till `18`, och kör *Utvecklarverktyg → Tillstånd →
   Uppdatera* på sensorn om du vill nolla testtillståndet (det skrivs annars
   över automatiskt vid nästa uppdatering).

Enskilda åtgärder (t.ex. Telegram) kan du testa löst under
*Utvecklarverktyg → Åtgärder*: klistra in åtgärden och tryck **Utför åtgärd**.

> HACS installerar bara `custom_components/`. Blueprintarna ligger i repot under
> `blueprints/automation/trelleborg_avfall/` och måste importeras enligt ovan –
> de följer inte med i HACS-nedladdningen.

### Telegram – du har det redan

Har du en Telegram-bot i Home Assistant behövs inget mer: varje tillåtet
chatt-ID får en egen **notify-entitet**. Kolla vad den heter under
*Utvecklarverktyg → Tillstånd* och sök på `notify.telegram`.

**Alternativ 1 – notify-entiteten (enklast).** I sista rutan, byt ut åtgärden mot:

```yaml
- action: notify.send_message
  entity_id: notify.telegram_bot_din_chatt
  data:
    title: "{{ trelleborg_title }}"
    message: "{{ trelleborg_message }}"
```

**Alternativ 2 – `telegram_bot.send_message`** om du vill styra formatering, tyst
avisering eller forumämne:

```yaml
- action: telegram_bot.send_message
  data:
    chat_id: 123456789
    message: "{{ trelleborg_message }}"
    title: "{{ trelleborg_title }}"
    disable_notification: true
    message_thread_id: 42        # bara om chatten är ett forum med ämnen
```

Saknas chatten: skicka ett meddelande till [@id_bot](https://t.me/id_bot) och
lägg till ID:t under **Inställningar → Enheter och tjänster → Telegram bot →
Lägg till tillåtet chatt-ID**. Notify-entiteten dyker upp direkt efteråt.

> `title` blir en extra rubrikrad i Telegram. Vill du hellre ha rubriken först i
> själva meddelandet tar du bort `title` och skriver
> `message: "{{ trelleborg_title }}\n{{ trelleborg_message }}"`.

Andra kanaler fungerar lika bra – byt bara ut åtgärden:

| Kanal | Åtgärd |
|---|---|
| Mobilappen | `notify.mobile_app_din_telefon` |
| Persistent notification | `notify.persistent_notification` |
| Högtalare | `tts.speak` / `media_player.play_media` |

### Variabler du kan använda

Texterna byggs av blueprinten och finns färdiga som `{{ trelleborg_title }}` och
`{{ trelleborg_message }}`.

**Påminnelsen:**

| Variabel | Exempel |
|---|---|
| `trelleborg_when` | `imorgon` (eller `idag`) |
| `trelleborg_date` | `2026-09-29` |
| `trelleborg_waste_types` | `Fyrfack 1, Restavfall` |
| `trelleborg_bins` | `370 l Fyrfackskärl, 190 l Kärl` |

**Översikten:** mallen går igenom `p` i `upcoming`, med `p.date`,
`p.waste_type`, `p.bin` och `p.days_until`.

## Hur det funkar

Portalen är en EDP FutureWeb-installation med två publika endpoints:

* `GetWastePickupSchedule` – JSON med **nästa** tömning per kärl, plus kärlets
  storlek, typ och frekvens.
* `DownloadWastePickup` – PDF med **hela** hämtschemat per kärl.

Integrationen hämtar båda och slår ihop dem på tjänste-ID, så kalendern visar
alla inplanerade tömningar och varje post vet vilken tunna det gäller.

Portalens adressökning returnerar inga träffar, så en inloggning behövs för att
läsa vilket fastighets-ID ditt kundnummer hör till. Det görs **en gång**; ID:t
sparas och därefter hämtas allt utan inloggning. BankID behövs inte –
integrationen använder portalens formulärinloggning med kundnummer och
personnummer.

PDF:en innehåller även namn och adress, men integrationen läser bara ut
kärlnamn, tjänste-ID och datum. Inget av det andra sparas eller loggas.

## Felsökning

| Symptom | Åtgärd |
|---|---|
| "Kombinationen … finns inte" | Kontrollera kundnummer och personnummer mot fakturan. Inga automatiska omförsök görs, eftersom portalen låser efter tre försök. |
| Bara en tömning per kärl i kalendern | Hämtschemat (PDF:en) kunde inte läsas. Integrationen faller då tillbaka på nästa tömning per kärl och försöker igen vid nästa intervall. |
| Sensorerna visar inget | Kontrollera att fastigheten har aktiva abonnemang i portalen. |
| Entiteterna blir otillgängliga | Portalen kan ligga nere. Integrationen försöker igen vid nästa intervall. |

## Licens

MIT
