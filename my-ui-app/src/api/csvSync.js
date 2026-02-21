import {
  createAddress,
  createCity,
  createClientSegment,
  createCountry,
  createGender,
  createManager,
  createManagerPosition,
  createOffice,
  createRegion,
  createSkill,
  createTicket,
  listAddresses,
  listCities,
  listClientSegments,
  listCountries,
  listGenders,
  listManagers,
  listManagerPositions,
  listOffices,
  listRegions,
  listSkills,
  listTickets,
} from "./backendCrud";

const normalize = (value) => String(value ?? "").trim().toLowerCase();

const isUuid = (value) =>
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    String(value || "").trim(),
  );

const parseLoad = (raw) => {
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 ? Math.round(value) : 0;
};

const getPositionHierarchy = (positionName) => {
  const key = normalize(positionName);
  if (key.includes("главн")) return 3;
  if (key.includes("ведущ")) return 2;
  if (key.includes("специал")) return 1;
  return 0;
};

const getSegmentPriority = (segmentName) => {
  const key = normalize(segmentName);
  if (key === "priority") return 10;
  if (key === "vip") return 5;
  return 0;
};

const createLocationCache = async () => ({
  countries: await listCountries(),
  regions: await listRegions(),
  cities: await listCities(),
  addresses: await listAddresses(),
});

const ensureCountry = async (cache, countryName) => {
  const name = (countryName || "Unknown Country").trim() || "Unknown Country";
  const found = cache.countries.find((country) => normalize(country.name) === normalize(name));
  if (found) return found.id_;

  const created = await createCountry({ name });
  cache.countries.push(created);
  return created.id_;
};

const ensureRegion = async (cache, regionName, countryId) => {
  const name = (regionName || "Unknown Region").trim() || "Unknown Region";
  const found = cache.regions.find(
    (region) => region.country_id === countryId && normalize(region.name) === normalize(name),
  );
  if (found) return found.id_;

  const created = await createRegion({ name, country_id: countryId });
  cache.regions.push(created);
  return created.id_;
};

const ensureCity = async (cache, cityName, regionId) => {
  const name = (cityName || "Unknown City").trim() || "Unknown City";
  const found = cache.cities.find(
    (city) => city.region_id === regionId && normalize(city.name) === normalize(name),
  );
  if (found) return found.id_;

  const created = await createCity({ name, region_id: regionId });
  cache.cities.push(created);
  return created.id_;
};

const ensureCityByName = async (cache, cityName) => {
  const name = (cityName || "").trim();
  if (!name) return null;

  const existing = cache.cities.find((city) => normalize(city.name) === normalize(name));
  if (existing) return existing.id_;

  const countryId = await ensureCountry(cache, "Unknown Country");
  const regionId = await ensureRegion(cache, "Unknown Region", countryId);
  return ensureCity(cache, name, regionId);
};

const ensureAddress = async (cache, address) => {
  const countryName = (address?.country || "Unknown Country").trim() || "Unknown Country";
  const regionName = (address?.region || "Unknown Region").trim() || "Unknown Region";
  const cityName = (address?.city || "Unknown City").trim() || "Unknown City";
  const street = (address?.street || "Unknown Street").trim() || "Unknown Street";
  const homeNumber = (
    address?.building ||
    address?.home_number ||
    "1"
  )
    .trim()
    || "1";

  const countryId = await ensureCountry(cache, countryName);
  const regionId = await ensureRegion(cache, regionName, countryId);
  const cityId = await ensureCity(cache, cityName, regionId);

  const found = cache.addresses.find(
    (item) =>
      item.country_id === countryId &&
      item.region_id === regionId &&
      item.city_id === cityId &&
      normalize(item.street) === normalize(street) &&
      normalize(item.home_number) === normalize(homeNumber),
  );

  if (found) return found.id_;

  const created = await createAddress({
    country_id: countryId,
    region_id: regionId,
    city_id: cityId,
    street,
    home_number: homeNumber,
  });

  cache.addresses.push(created);
  return created.id_;
};

const ensurePosition = async (cache, positionName) => {
  const name = (positionName || "Specialist").trim() || "Specialist";
  const found = cache.positions.find((position) => normalize(position.name) === normalize(name));
  if (found) return found.id_;

  const created = await createManagerPosition({
    name,
    hierarchy_level: getPositionHierarchy(name),
  });

  cache.positions.push(created);
  return created.id_;
};

const ensureSkill = async (cache, skillName) => {
  const name = String(skillName || "").trim().toUpperCase();
  if (!name) return null;

  const found = cache.skills.find((skill) => normalize(skill.name) === normalize(name));
  if (found) return found.id_;

  const created = await createSkill({ name });
  cache.skills.push(created);
  return created.id_;
};

const ensureGender = async (cache, genderName = "Unknown") => {
  const name = (genderName || "Unknown").trim() || "Unknown";
  const found = cache.genders.find((gender) => normalize(gender.name) === normalize(name));
  if (found) return found.id_;

  const created = await createGender({ name });
  cache.genders.push(created);
  return created.id_;
};

const ensureClientSegment = async (cache, segmentName) => {
  const name = (segmentName || "Mass").trim() || "Mass";
  const found = cache.segments.find((segment) => normalize(segment.name) === normalize(name));
  if (found) return found.id_;

  const created = await createClientSegment({
    name,
    priority: getSegmentPriority(name),
  });

  cache.segments.push(created);
  return created.id_;
};

export const syncManagersFromCsv = async (rows = []) => {
  const summary = { created: 0, skipped: 0, failed: 0, errors: [] };
  if (!rows.length) return summary;

  const [positions, skills, existingManagers] = await Promise.all([
    listManagerPositions(),
    listSkills(),
    listManagers({ expand_position: false, expand_city: false, expand_skills: true }),
  ]);

  const locationCache = await createLocationCache();
  const cache = { positions, skills };

  const managerSignatureSet = new Set(
    existingManagers.map((manager) => {
      const skillIds = (manager.skills || []).map((s) => s.id_).sort((a, b) => a - b);
      return `${manager.position_id || 0}|${manager.city_id || 0}|${manager.in_progress_requests || 0}|${skillIds.join(",")}`;
    }),
  );

  for (const row of rows) {
    try {
      const positionId = await ensurePosition(cache, row.position);
      const cityId = await ensureCityByName(locationCache, row.office);

      const skillIds = [];
      for (const skill of row.skills || []) {
        const skillId = await ensureSkill(cache, skill);
        if (skillId) skillIds.push(skillId);
      }
      skillIds.sort((a, b) => a - b);

      const load = parseLoad(row.current_load);
      const signature = `${positionId || 0}|${cityId || 0}|${load}|${skillIds.join(",")}`;
      if (managerSignatureSet.has(signature)) {
        summary.skipped += 1;
        continue;
      }

      const payload = {
        position_id: positionId,
        in_progress_requests: load,
        skill_ids: skillIds,
      };
      if (cityId) payload.city_id = cityId;

      await createManager(payload, {
        expand_position: true,
        expand_city: true,
        expand_skills: true,
      });

      managerSignatureSet.add(signature);
      summary.created += 1;
    } catch (error) {
      summary.failed += 1;
      summary.errors.push(`Manager sync error: ${error.message}`);
    }
  }

  return summary;
};

export const syncBusinessUnitsFromCsv = async (rows = []) => {
  const summary = { created: 0, skipped: 0, failed: 0, errors: [] };
  if (!rows.length) return summary;

  const [existingOffices, locationCache] = await Promise.all([
    listOffices({ expand_city: true }),
    createLocationCache(),
  ]);

  const officeSignatureSet = new Set(
    existingOffices.map((office) => `${office.city_id || 0}|${normalize(office.address)}`),
  );

  for (const row of rows) {
    try {
      const cityId = await ensureCityByName(locationCache, row.office);
      const address = (row.address || row.office || "Unknown address").trim() || "Unknown address";
      const signature = `${cityId || 0}|${normalize(address)}`;

      if (officeSignatureSet.has(signature)) {
        summary.skipped += 1;
        continue;
      }

      const payload = { address };
      if (cityId) payload.city_id = cityId;

      await createOffice(payload);
      officeSignatureSet.add(signature);
      summary.created += 1;
    } catch (error) {
      summary.failed += 1;
      summary.errors.push(`Business unit sync error: ${error.message}`);
    }
  }

  return summary;
};

export const syncTicketsFromCsv = async (rows = []) => {
  const summary = { created: 0, skipped: 0, failed: 0, errors: [] };
  if (!rows.length) return summary;

  const [existingTickets, genders, segments] = await Promise.all([
    listTickets({
      expand: false,
      include_attachments: false,
      include_attachment_type: false,
      include_attachment_url: false,
    }),
    listGenders(),
    listClientSegments(),
  ]);

  const locationCache = await createLocationCache();
  const ticketIdSet = new Set(existingTickets.map((ticket) => String(ticket.id_).toLowerCase()));
  const cache = { genders, segments };

  const fallbackGenderId = await ensureGender(cache, "Unknown");

  for (const row of rows) {
    try {
      const segmentId = await ensureClientSegment(cache, row.segment);
      const addressId = await ensureAddress(locationCache, row.address || {});

      const parsedTicketId = String(row.ticket_id || "").trim();
      const validUuid = isUuid(parsedTicketId) ? parsedTicketId.toLowerCase() : null;

      if (validUuid && ticketIdSet.has(validUuid)) {
        summary.skipped += 1;
        continue;
      }

      const payload = {
        gender_id: fallbackGenderId,
        date_of_birth: "2000-01-01",
        description: row.description || "",
        segment_id: segmentId,
        address_id: addressId,
        attachment_ids: [],
      };

      if (validUuid) payload.id_ = validUuid;

      await createTicket(payload, {
        expand: true,
        include_attachments: true,
        include_attachment_type: true,
        include_attachment_url: false,
      });

      if (validUuid) ticketIdSet.add(validUuid);
      summary.created += 1;
    } catch (error) {
      summary.failed += 1;
      summary.errors.push(`Ticket sync error: ${error.message}`);
    }
  }

  return summary;
};

export const syncParsedCsvToBackend = async (type, parsedResult) => {
  if (type === "managers") return syncManagersFromCsv(parsedResult?.managers || []);
  if (type === "businessUnits") return syncBusinessUnitsFromCsv(parsedResult?.units || []);
  if (type === "tickets") return syncTicketsFromCsv(parsedResult?.tickets || []);

  return { created: 0, skipped: 0, failed: 0, errors: [] };
};
