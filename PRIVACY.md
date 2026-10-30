# Privacy policy — Modbus Slave for Home Assistant

**[English](#english)** · **[Nederlands](#nederlands)**

Last updated: 30 October 2026. Applies to the usage statistics (on by default, opt-out), available from version 1.0.0.

---

## English

### In short

The integration only sends data while **Share usage statistics** is ticked. It is ticked by default when you add the integration, and you can untick it on that same page or later with **Reconfigure**. When it is on, Home Assistant sends a tiny report every 6 hours that contains nothing but a random installation ID. It is used only to count how many installations are active and in which countries. Nothing about Modbus, your entities, your network or your Home Assistant is sent.

### Who is responsible

BRDC ([brdc.nl](https://brdc.nl)), the maintainer of this integration, is the controller. Questions and requests: [contact@brianrodriguez.nl](mailto:contact@brianrodriguez.nl).

### What is sent

While at least one Modbus Slave entry has the option ticked, one report every 6 hours (the first about 10 minutes after Home Assistant starts) goes to `ha-modbus.telemetry.brdc.nl`.

| Field | Example | Meaning |
|---|---|---|
| `schema` | `1` | Report format version |
| `install_id` | `3f2b…` | A random ID the integration creates once. Not derived from your Home Assistant or your network |

**Never sent:** IP addresses, ports, slave IDs, entity IDs, mappings, register values, versions, or anything else about your Home Assistant setup.

### What the server adds

- The **country** your report came from (a two-letter code). It is looked up in a local database on our own server; no third party is contacted.
- The **date** the report arrived (no time of day), and the dates an installation was first and last seen.
- A **marker** that your installation is currently active, used only to count how many installations are active right now. It is stored securely and separately from your installation ID, holds no time history, and is deleted automatically within 8 hours of your latest report.

### Your IP address

Your IP address is used only while your report is received: to look up your country (in a local database, no third party) and for rate limiting. It is never stored. Rate limiting uses a keyed hash of your IP address, not the address itself, which is deleted automatically within one hour. The web server for this address keeps no access logs.

### Why, and on what basis

To know how many installations use this integration and where, so the time spent on maintenance and support goes where it matters. Nothing from the reports ever becomes public except totals (number of installations, number per country). The legal basis is our legitimate interest in knowing how widely the integration is used (GDPR art. 6(1)(f)): the data is minimal, contains no names, addresses or values, and you can object at any time by unticking the option.

### Pseudonymous, not anonymous

We cannot see who you are. But the installation ID stays the same, so its reports can be linked to each other. That is why we treat the reports as personal data.

### How long

Reports are kept indefinitely, to follow usage over time.

### Where

On servers in the EU, run by a hosting provider that processes the data on our behalf. No other parties receive it.

### Stopping, access and deletion

- **Stop:** untick the option with **Settings → Devices & services → Modbus Slave → ⋮ → Reconfigure**, for every Modbus Slave entry. No further reports are sent.
- **Access or deletion:** we do not know which installation ID is yours, so we cannot find your data on our own. Send us your installation ID and we will send you the stored reports or delete all of them. You find the ID in your Home Assistant configuration folder, in the file `.storage/modbus_slave.telemetry`, under `install_id`. Do not post it in a public GitHub issue. The active marker is not part of a deletion; it expires on its own.
- **Complaints:** you can contact the data protection authority in your country. In the Netherlands that is the Autoriteit Persoonsgegevens.

### Changes

Changes to this policy are made in this file and are visible in its history on GitHub. New kinds of data are only collected after this policy has been updated.

---

## Nederlands

### In het kort

De integratie stuurt alleen gegevens zolang **Gebruiksstatistieken delen** is aangevinkt. Bij het toevoegen van de integratie staat het standaard aan; je kunt het op die pagina uitvinken, of later via **Opnieuw configureren**. Staat het aan, dan stuurt Home Assistant elke 6 uur een heel klein rapport met niets anders dan een willekeurige installatie-ID. Dat wordt alleen gebruikt om te tellen hoeveel installaties actief zijn en in welke landen. Er wordt niets verstuurd over Modbus, je entities, je netwerk of je Home Assistant.

### Wie is verantwoordelijk

BRDC ([brdc.nl](https://brdc.nl)), de maker van deze integratie, is verwerkingsverantwoordelijke. Vragen en verzoeken: [contact@brianrodriguez.nl](mailto:contact@brianrodriguez.nl).

### Wat er verstuurd wordt

Zolang bij minstens één Modbus Slave-entry de optie aan staat, gaat er elke 6 uur één rapport (het eerste ongeveer 10 minuten na het starten van Home Assistant) naar `ha-modbus.telemetry.brdc.nl`.

| Veld | Voorbeeld | Betekenis |
|---|---|---|
| `schema` | `1` | Versie van het rapportformaat |
| `install_id` | `3f2b…` | Een willekeurige ID die de integratie één keer aanmaakt. Niet afgeleid van je Home Assistant of je netwerk |

**Nooit verstuurd:** IP-adressen, poorten, slave-ID's, entity-ID's, mappings, registerwaarden, versies, of iets anders over je Home Assistant-installatie.

### Wat de server toevoegt

- Het **land** waar je rapport vandaan kwam (een code van twee letters). Dat wordt opgezocht in een lokale database op onze eigen server; er wordt geen derde partij benaderd.
- De **datum** waarop het rapport binnenkwam (zonder tijdstip), en de datums waarop een installatie voor het eerst en het laatst gezien is.
- Een **marker** dat je installatie nu actief is, alleen gebruikt om te tellen hoeveel installaties op dit moment actief zijn. Die wordt veilig en los van je installatie-ID opgeslagen, bevat geen tijdgeschiedenis en wordt automatisch verwijderd binnen 8 uur na je laatste rapport.

### Je IP-adres

Je IP-adres wordt alleen gebruikt tijdens het ontvangen van je rapport: om je land op te zoeken (in een lokale database, geen derde partij) en voor rate limiting. Het wordt nooit opgeslagen. Voor rate limiting gebruiken we een beveiligde hash van je IP-adres, niet het adres zelf, die binnen een uur automatisch wordt verwijderd. De webserver voor dit adres houdt geen toegangslogs bij.

### Waarom, en op welke grond

Om te weten hoeveel installaties deze integratie gebruiken en waar, zodat de tijd voor onderhoud en ondersteuning gaat naar waar het telt. Uit de rapporten wordt nooit iets openbaar behalve totalen (aantal installaties, aantal per land). De grondslag is ons gerechtvaardigd belang om te weten hoe breed de integratie gebruikt wordt (AVG art. 6 lid 1 onder f): de gegevens zijn minimaal, bevatten geen namen, adressen of waarden, en je kunt op elk moment bezwaar maken door de optie uit te vinken.

### Pseudoniem, niet anoniem

We kunnen niet zien wie je bent. Maar de installatie-ID blijft hetzelfde, dus de rapporten ervan zijn aan elkaar te koppelen. Daarom behandelen we de rapporten als persoonsgegevens.

### Hoe lang

Rapporten worden onbeperkt bewaard, om het gebruik door de tijd te volgen.

### Waar

Op servers in de EU, beheerd door een hostingpartij die de gegevens in onze opdracht verwerkt. Geen andere partijen ontvangen ze.

### Stoppen, inzage en verwijderen

- **Stoppen:** vink de optie uit via **Instellingen → Apparaten en diensten → Modbus Slave → ⋮ → Opnieuw configureren**, voor elke Modbus Slave-entry. Er worden dan geen rapporten meer verstuurd.
- **Inzage of verwijderen:** we weten niet welke installatie-ID van jou is, dus we kunnen je gegevens niet zelf vinden. Stuur ons je installatie-ID en we sturen je de opgeslagen rapporten of verwijderen ze allemaal. Je vindt de ID in je Home Assistant-configuratiemap, in het bestand `.storage/modbus_slave.telemetry`, onder `install_id`. Zet hem niet in een openbaar GitHub-issue. De actief-marker valt niet onder verwijderen; die verloopt vanzelf.
- **Klachten:** je kunt terecht bij de privacytoezichthouder in je land. In Nederland is dat de Autoriteit Persoonsgegevens.

### Wijzigingen

Wijzigingen in deze verklaring gebeuren in dit bestand en zijn zichtbaar in de geschiedenis op GitHub. Nieuwe soorten gegevens worden pas verzameld nadat deze verklaring is bijgewerkt.
