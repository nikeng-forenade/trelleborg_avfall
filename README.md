# Trelleborg Avfall

Home Assistant-integration som hämtar dina tömningsdagar från
[Kretslopp och vatten, Trelleborgs kommun](https://www.trelleborg.se/bygga-bo-miljo/avfall-och-atervinning/).

**Fristående** – den har inget med `waste_collection_schedule` att göra och kan
köras samtidigt som, eller i stället för, den.

## Vad du får

| Entitet | Vad den gör |
|---|---|
| `sensor.*_nasta_tomning` | Datum för nästa tömning (attribut: typ, kärl, frekvens, dagar kvar och listan `upcoming`) |
| `binary_sensor.*_tomning_idag` | På hela tömningsdagen |
| `binary_sensor.*_tomning_imorgon` | På hela dagen innan |
| `calendar.*_tomningar` | Alla tömningar som heldagshändelser |

De två binära sensorerna slår om strax efter midnatt, så automationer med
`to: "on"` körs rätt dag.

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

Portalen är en EDP FutureWeb-installation. Tömningsdagarna ligger på en publik
endpoint, men portalens adressökning returnerar inga träffar – därför loggar
integrationen in **en gång** för att läsa vilket fastighets-ID ditt kundnummer
hör till. ID:t sparas, och därefter hämtas schemat utan inloggning. Portalen
belastas alltså minimalt och inloggningen används bara igen om schemat inte
längre går att läsa.

BankID behövs inte; integrationen använder portalens formulärinloggning med
kundnummer och personnummer.

## Felsökning

| Symptom | Åtgärd |
|---|---|
| "Kombinationen … finns inte" | Kontrollera kundnummer och personnummer mot fakturan. Inga automatiska omförsök görs, eftersom portalen låser efter tre försök. |
| Sensorerna visar inget | Kontrollera att fastigheten har aktiva abonnemang i portalen. |
| Entiteterna blir otillgängliga | Portalen kan ligga nere. Integrationen försöker igen vid nästa intervall. |

## Licens

MIT
