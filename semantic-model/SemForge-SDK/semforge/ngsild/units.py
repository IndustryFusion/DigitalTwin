"""NGSI-LD unit codes: a curated set of UN/CEFACT Recommendation 20 codes.

An NGSI-LD Property says its unit with `unitCode`, a Rec 20 *common code*
(`CEL`, `BAR`, `KMH`) -- three characters that say nothing to a reader. So
each code here carries what it is: its name, its symbol, and the quantity it
measures, as QUDT names quantities (http://qudt.org/vocab/quantitykind/).
That is what makes a code findable by what you know: "temperature" finds
CEL, FAH and KEL; "celsius" finds CEL.

The set is curated, not Rec 20 entire: about 120 engineering units across
temperature, pressure, length, area, volume, mass, time, speed, flow, force,
energy, power, electricity, frequency, ratio and data. Rec 20 has some 2000
codes, most of them a search would only bury the right one under; a unit
missing here is added to the package's own knowledge as a `qudt:Unit`, with
the same terms (cooked/units.py).
"""

from rdflib import Namespace

QUDT = Namespace('http://qudt.org/schema/qudt/')
QUANTITYKIND = Namespace('http://qudt.org/vocab/quantitykind/')

# (common code, name, symbol, QUDT quantity kind)
CATALOGUE = (
    # temperature
    ('CEL', 'degree Celsius', '°C', 'Temperature'),
    ('FAH', 'degree Fahrenheit', '°F', 'Temperature'),
    ('KEL', 'kelvin', 'K', 'Temperature'),
    # pressure
    ('PAL', 'pascal', 'Pa', 'Pressure'),
    ('KPA', 'kilopascal', 'kPa', 'Pressure'),
    ('MPA', 'megapascal', 'MPa', 'Pressure'),
    ('A97', 'hectopascal', 'hPa', 'Pressure'),
    ('BAR', 'bar', 'bar', 'Pressure'),
    ('MBR', 'millibar', 'mbar', 'Pressure'),
    ('ATM', 'standard atmosphere', 'atm', 'Pressure'),
    ('PS', 'pound-force per square inch', 'psi', 'Pressure'),
    # length
    ('MTR', 'metre', 'm', 'Length'),
    ('KMT', 'kilometre', 'km', 'Length'),
    ('DMT', 'decimetre', 'dm', 'Length'),
    ('CMT', 'centimetre', 'cm', 'Length'),
    ('MMT', 'millimetre', 'mm', 'Length'),
    ('4H', 'micrometre', 'µm', 'Length'),
    ('C45', 'nanometre', 'nm', 'Length'),
    ('INH', 'inch', 'in', 'Length'),
    ('FOT', 'foot', 'ft', 'Length'),
    ('YRD', 'yard', 'yd', 'Length'),
    ('SMI', 'mile (statute mile)', 'mi', 'Length'),
    ('NMI', 'nautical mile', 'NM', 'Length'),
    # area
    ('MTK', 'square metre', 'm²', 'Area'),
    ('KMK', 'square kilometre', 'km²', 'Area'),
    ('CMK', 'square centimetre', 'cm²', 'Area'),
    ('MMK', 'square millimetre', 'mm²', 'Area'),
    ('HAR', 'hectare', 'ha', 'Area'),
    ('INK', 'square inch', 'in²', 'Area'),
    ('FTK', 'square foot', 'ft²', 'Area'),
    # volume
    ('MTQ', 'cubic metre', 'm³', 'Volume'),
    ('DMQ', 'cubic decimetre', 'dm³', 'Volume'),
    ('CMQ', 'cubic centimetre', 'cm³', 'Volume'),
    ('MMQ', 'cubic millimetre', 'mm³', 'Volume'),
    ('LTR', 'litre', 'l', 'Volume'),
    ('MLT', 'millilitre', 'ml', 'Volume'),
    ('HLT', 'hectolitre', 'hl', 'Volume'),
    ('GLL', 'gallon (US)', 'gal (US)', 'Volume'),
    ('GLI', 'gallon (UK)', 'gal (UK)', 'Volume'),
    # mass
    ('KGM', 'kilogram', 'kg', 'Mass'),
    ('GRM', 'gram', 'g', 'Mass'),
    ('MGM', 'milligram', 'mg', 'Mass'),
    ('MC', 'microgram', 'µg', 'Mass'),
    ('TNE', 'tonne (metric ton)', 't', 'Mass'),
    ('LBR', 'pound', 'lb', 'Mass'),
    ('ONZ', 'ounce (avoirdupois)', 'oz', 'Mass'),
    # time
    ('SEC', 'second', 's', 'Time'),
    ('C26', 'millisecond', 'ms', 'Time'),
    ('B98', 'microsecond', 'µs', 'Time'),
    ('C47', 'nanosecond', 'ns', 'Time'),
    ('MIN', 'minute', 'min', 'Time'),
    ('HUR', 'hour', 'h', 'Time'),
    ('DAY', 'day', 'd', 'Time'),
    ('WEE', 'week', 'wk', 'Time'),
    ('MON', 'month', 'mo', 'Time'),
    ('ANN', 'year', 'y', 'Time'),
    # speed and acceleration
    ('MTS', 'metre per second', 'm/s', 'Speed'),
    ('2X', 'metre per minute', 'm/min', 'Speed'),
    ('KMH', 'kilometre per hour', 'km/h', 'Speed'),
    ('HM', 'mile per hour (statute mile)', 'mile/h', 'Speed'),
    ('KNT', 'knot', 'kn', 'Speed'),
    ('MSK', 'metre per second squared', 'm/s²', 'Acceleration'),
    # rotation, frequency, angle
    ('HTZ', 'hertz', 'Hz', 'Frequency'),
    ('KHZ', 'kilohertz', 'kHz', 'Frequency'),
    ('MHZ', 'megahertz', 'MHz', 'Frequency'),
    ('A86', 'gigahertz', 'GHz', 'Frequency'),
    ('RPM', 'revolutions per minute', 'r/min', 'AngularVelocity'),
    ('DD', 'degree (unit of angle)', '°', 'PlaneAngle'),
    ('C81', 'radian', 'rad', 'PlaneAngle'),
    # flow
    ('MQS', 'cubic metre per second', 'm³/s', 'VolumeFlowRate'),
    ('MQH', 'cubic metre per hour', 'm³/h', 'VolumeFlowRate'),
    ('L2', 'litre per minute', 'l/min', 'VolumeFlowRate'),
    ('G2', 'US gallon per minute', 'gal (US)/min', 'VolumeFlowRate'),
    ('KGS', 'kilogram per second', 'kg/s', 'MassFlowRate'),
    ('E93', 'kilogram per hour', 'kg/h', 'MassFlowRate'),
    # density
    ('KMQ', 'kilogram per cubic metre', 'kg/m³', 'Density'),
    ('23', 'gram per cubic centimetre', 'g/cm³', 'Density'),
    # force and torque
    ('NEW', 'newton', 'N', 'Force'),
    ('B47', 'kilonewton', 'kN', 'Force'),
    ('NU', 'newton metre', 'N·m', 'Torque'),
    # energy
    ('JOU', 'joule', 'J', 'Energy'),
    ('KJO', 'kilojoule', 'kJ', 'Energy'),
    ('3B', 'megajoule', 'MJ', 'Energy'),
    ('WHR', 'watt hour', 'W·h', 'Energy'),
    ('KWH', 'kilowatt hour', 'kW·h', 'Energy'),
    ('MWH', 'megawatt hour (1000 kW·h)', 'MW·h', 'Energy'),
    ('GWH', 'gigawatt hour', 'GW·h', 'Energy'),
    ('BTU', 'British thermal unit (international table)', 'Btu', 'Energy'),
    # power
    ('WTT', 'watt', 'W', 'Power'),
    ('C31', 'milliwatt', 'mW', 'Power'),
    ('KWT', 'kilowatt', 'kW', 'Power'),
    ('MAW', 'megawatt', 'MW', 'Power'),
    ('A90', 'gigawatt', 'GW', 'Power'),
    ('D46', 'volt - ampere', 'V·A', 'ApparentPower'),
    ('KVA', 'kilovolt - ampere', 'kV·A', 'ApparentPower'),
    # electricity
    ('AMP', 'ampere', 'A', 'ElectricCurrent'),
    ('4K', 'milliampere', 'mA', 'ElectricCurrent'),
    ('VLT', 'volt', 'V', 'Voltage'),
    ('2Z', 'millivolt', 'mV', 'Voltage'),
    ('KVT', 'kilovolt', 'kV', 'Voltage'),
    ('OHM', 'ohm', 'Ω', 'Resistance'),
    ('B49', 'kilohm', 'kΩ', 'Resistance'),
    ('SIE', 'siemens', 'S', 'Conductance'),
    ('FAR', 'farad', 'F', 'Capacitance'),
    ('COU', 'coulomb', 'C', 'ElectricCharge'),
    ('AMH', 'ampere hour', 'A·h', 'ElectricCharge'),
    # light and sound
    ('LUX', 'lux', 'lx', 'Illuminance'),
    ('LUM', 'lumen', 'lm', 'LuminousFlux'),
    ('CDL', 'candela', 'cd', 'LuminousIntensity'),
    ('2N', 'decibel', 'dB', 'SoundPressureLevel'),
    # amount, ratio, count
    ('C34', 'mole', 'mol', 'AmountOfSubstance'),
    ('P1', 'percent', '%', 'DimensionlessRatio'),
    ('59', 'part per million', 'ppm', 'DimensionlessRatio'),
    ('61', 'part per billion (US)', 'ppb', 'DimensionlessRatio'),
    ('C62', 'one', '1', 'Dimensionless'),
    ('H87', 'piece', 'pc', 'Count'),
    # data
    ('A99', 'bit', 'bit', 'InformationEntropy'),
    ('AD', 'byte', 'B', 'InformationEntropy'),
    ('2P', 'kilobyte', 'kB', 'InformationEntropy'),
    ('4L', 'megabyte', 'MB', 'InformationEntropy'),
    ('E34', 'gigabyte', 'GB', 'InformationEntropy'),
)


def quantity_words(kind):
    """'VolumeFlowRate' -> 'volume flow rate': how a person searches for it."""
    out = ''
    for index, char in enumerate(kind):
        if char.isupper() and index and not kind[index - 1].isupper():
            out += ' '
        out += char.lower()
    return out
