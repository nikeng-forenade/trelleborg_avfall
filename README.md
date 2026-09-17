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

**Integrationskortet → Konfigurera** låter dig ställa hur ofta nya tider hämtas
(15 minuter till 7 dagar, standard 12 timmar). Tömningsdagarna ändras sällan, så
ett långt intervall räcker och belastar portalen mindre.

## Automationer

Vill du ha med **vilken tunna** det gäller i meddelandet använder du `bins` i
stället för `waste_types` – samma uppbyggnad, se attributtabellen ovan.

### Påminnelse dagen innan

```yaml
automation:
  - alias: Påminnelse kvällen innan tömning
    triggers:
      - trigger: state
        entity_id: binary_sensor.trelleborg_avfall_tomning_imorgon
        to: "on"
    actions:
      - action: notify.mobile_app_din_telefon
        data:
          title: "Tömning imorgon"
          message: >-
            {{ state_attr('binary_sensor.trelleborg_avfall_tomning_imorgon',
               'waste_types') | join(', ') }}
```

### Åtgärd på tömningsdagen

```yaml
automation:
  - alias: Ställ ut kärlet
    triggers:
      - trigger: state
        entity_id: binary_sensor.trelleborg_avfall_tomning_idag
        to: "on"
    actions:
      - action: notify.mobile_app_din_telefon
        data:
          message: >-
            Idag töms: {{ state_attr('binary_sensor.trelleborg_avfall_tomning_idag',
            'waste_types') | join(', ') }}
```

### Bara vissa avfallstyper

```yaml
    triggers:
      - trigger: state
        entity_id: binary_sensor.trelleborg_avfall_tomning_imorgon
        to: "on"
    conditions:
      - condition: template
        value_template: >-
          {{ 'Trädgårdsavfall' in state_attr(
             'binary_sensor.trelleborg_avfall_tomning_imorgon', 'waste_types') }}
```

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
