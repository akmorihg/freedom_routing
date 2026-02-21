class SmartWRRRouter:
    def __init__(self, managers):
        self.managers = managers
        self.last_assigned_id = None

        # Capacity coefficients (higher = can handle more load)
        self.capacity = {
            "Специалист": 1.0,
            "Ведущий специалист": 1.3,
            "Глав специалист": 1.6
        }

        # Segment priority weights
        self.segment_weight = {
            "VIP": 10,
            "Priority": 5,
            "Mass": 0
        }

    # Ticket priority calculation
    def calculate_ticket_weight(self, urgency_score, client_segment, attachment):
        seg_weight = self.segment_weight.get(client_segment, 0)
        return urgency_score + seg_weight + attachment

    # Filter managers
    def filter_managers(self, ticket):

        language = ticket["language"]
        segment = ticket["client_segment"]

        pool = []

        for m in self.managers:

            # Language filtering (mandatory)
            if language not in m["skills"]:
                continue

            # VIP / Priority handling
            if segment in ["VIP", "Priority"]:
                if "VIP" not in m["skills"]:
                    continue
            else:
                # Mass → everyone allowed
                pass

            pool.append(m)

        return pool

    # Effective load (normalized by capacity)
    def effective_load(self, manager):
        cap = self.capacity.get(manager["position"], 1.0)
        return manager["current_load"] / cap

    def distribute_ticket(self, ticket):

        urgency_score = ticket["urgency_score"]
        client_segment = ticket["client_segment"]
        attachment = ticket["attachment"]

        # filter managers
        pool = self.filter_managers(ticket)
        if not pool:
            return "Routing Error: No qualified managers available."

        # select top 2 less loaded managers
        pool.sort(key=lambda m: self.effective_load(m))
        top_candidates = pool[:2]

        if len(top_candidates) == 1:
            selected = top_candidates[0]
        else:
            if self.last_assigned_id == top_candidates[0]["id"]:
                selected = top_candidates[1]
            else:
                selected = top_candidates[0]

        # calculate ticket weight
        ticket_weight = self.calculate_ticket_weight(urgency_score, client_segment, attachment)

        # update manager load
        selected["current_load"] += ticket_weight

        # update RR state
        self.last_assigned_id = selected["id"]

        return {
            "assigned_to": selected["name"],
            "ticket_weight": ticket_weight,
            "manager_new_load": round(selected["current_load"], 2),
            "manager_effective_load": round(self.effective_load(selected), 2)
        }