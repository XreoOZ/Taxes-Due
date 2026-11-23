"""
Production Distribution System
Calculates dynamic household shares and distributes production output into household storage
based on participating worker counts. Handles fractional shares and indivisible quantities consistently.
"""

class ProductionDistributionSystem:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # Persistent remainder credit tracking per workplace/activity
        # workplace_id -> {household_id: float_credit}
        self.remainder_credits = {}

        # Household production statistics & history
        # household_id -> {
        #     "total_produced": {resource_name: int},
        #     "workplaces": set(),
        #     "history": [ {"day": int, "resource": str, "amount": int, "workplace": str} ]
        # }
        self.household_records = {}

    def get_participating_household_counts(self, participating_workers, villager_manager=None):
        """
        Determines the worker count per household from participating workers.
        participating_workers can be:
        - dict of {household_id: worker_count}
        - list of Villager objects (with .family_id or .household_id)
        - list of worker_ids (resolved against villager_manager)
        Returns: ({household_id: count}, total_workers)
        """
        if isinstance(participating_workers, dict):
            counts = {str(k): int(v) for k, v in participating_workers.items() if v > 0}
            return counts, sum(counts.values())

        counts = {}
        if not participating_workers:
            return counts, 0

        for w in participating_workers:
            fam_id = None
            if hasattr(w, "family_id") and getattr(w, "family_id") is not None:
                fam_id = getattr(w, "family_id")
            elif hasattr(w, "household_id") and getattr(w, "household_id") is not None:
                fam_id = getattr(w, "household_id")
            elif isinstance(w, (str, int)):
                w_str = str(w)
                if villager_manager:
                    for f in getattr(villager_manager, "families", []):
                        if any(str(getattr(m, "id", "")) == w_str for m in f.members):
                            fam_id = f.id
                            break
                if fam_id is None:
                    # Treat worker ID itself as household identifier if not in villager_manager
                    fam_id = w_str

            if fam_id is not None:
                fam_str = str(fam_id)
                counts[fam_str] = counts.get(fam_str, 0) + 1

        total_workers = sum(counts.values())
        return counts, total_workers

    def calculate_shares(self, participating_workers, villager_manager=None):
        """
        Formula: Household share = Household participating worker count / Total participating worker count.
        Returns:
            dict of {household_id: float_share} (e.g. {"fam_A": 0.4, "fam_B": 0.6})
        """
        counts, total_workers = self.get_participating_household_counts(participating_workers, villager_manager)
        if total_workers == 0:
            return {}
        return {h: counts[h] / total_workers for h in counts}

    def calculate_distribution(self, total_amount, participating_workers, villager_manager=None, workplace_id=None):
        """
        Distributes total_amount discrete items among participating households.
        Uses Largest Remainder (Hamilton-Hare) Method with persistent credit tracking
        to handle fractional shares and indivisible quantities consistently.

        Guarantees:
        - sum(distributed.values()) == total_amount (ZERO LOSS, ZERO DUPLICATION)
        - Handles any number of households
        - Proportional to worker count
        """
        counts, total_workers = self.get_participating_household_counts(participating_workers, villager_manager)
        if total_workers == 0 or total_amount <= 0:
            return {h: 0 for h in counts}

        shares = {h: counts[h] / total_workers for h in counts}

        # Retrieve or initialize persistent credit accumulator for this workplace/activity
        wp_key = str(workplace_id) if workplace_id is not None else "generic_workplace"
        if wp_key not in self.remainder_credits:
            self.remainder_credits[wp_key] = {}
        credits = self.remainder_credits[wp_key]
        for h in counts:
            if h not in credits:
                credits[h] = 0.0

        # Calculate exact shares for this production amount
        exact_shares = {h: total_amount * shares[h] for h in counts}

        # Base integer allocation
        base_alloc = {h: int(exact_shares[h]) for h in counts}
        allocated_sum = sum(base_alloc.values())
        remainder_items = total_amount - allocated_sum

        # Fractional parts
        frac_parts = {h: exact_shares[h] - base_alloc[h] for h in counts}

        # Priority score = current credit + fractional part
        # Stable sort: descending by score, ascending by household ID for deterministic resolution
        scores = [(credits[h] + frac_parts[h], h) for h in counts]
        scores.sort(key=lambda item: (-item[0], item[1]))

        # Distribute indivisible remainder items to top-scoring households
        result = dict(base_alloc)
        for i in range(remainder_items):
            winner_h = scores[i][1]
            result[winner_h] += 1

        # Update persistent credits for next distribution
        # new_credit = old_credit + exact_share - allocated_amount
        for h in counts:
            credits[h] = credits[h] + exact_shares[h] - result[h]

        return result

    def deposit_to_household_storage(self, household_id, resource_name, amount, furniture_manager=None, stockpile_manager=None, permit_manager=None, villager_manager=None):
        """
        Deposits the allocated amount into the household's OWN storage.
        1. Checks furniture_manager for household_storage chest.
        2. If no chest, drops at household's deed permit or home location via stockpile_manager.
        Returns: (success: bool, target_type: "chest"|"ground"|"none", details: Any)
        """
        if amount <= 0:
            return True, "none", None

        fam_str = str(household_id)

        # 1. Household Storage Chest
        if furniture_manager:
            chest = furniture_manager.get_storage_for_family(fam_str, villager_manager=villager_manager, permit_manager=permit_manager)
            if chest:
                chest.store_item(resource_name, amount)
                return True, "chest", chest

        # 2. Ground Stack at Household Deed / Location
        if stockpile_manager:
            gx, gy = 0, 0
            if permit_manager:
                fam = villager_manager.get_family_by_id(fam_str) if villager_manager else None
                assigned_pid = getattr(fam, "assigned_permit_id", None) if fam else None
                if assigned_pid:
                    p = next((p for p in permit_manager.permits if p.id == assigned_pid), None)
                    if p:
                        # Prefer an open tile inside the permit (not buried
                        # under the home building footprint) so family
                        # members can actually reach the stack.
                        from game.world.permits import resolve_household_ground_drop_tile
                        resolved = resolve_household_ground_drop_tile(
                            assigned_pid, permit_manager, None,
                            furniture_manager=furniture_manager)
                        gx, gy = resolved if resolved else (p.grid_x, p.grid_y)
            stockpile_manager.drop_resource(resource_name, amount, gx, gy, owner_type="villager", owner_id=fam_str)
            return True, "ground", (gx, gy)

        return False, "failed", None

    def distribute_production(self, resource_name, amount, participating_workers, furniture_manager=None, stockpile_manager=None, permit_manager=None, villager_manager=None, workplace_id=None, day_number=1, auto_deposit=True):
        """
        Distributes production output according to calculated proportions.
        Work generically across all professions and production activities.
        """
        counts, total_w = self.get_participating_household_counts(participating_workers, villager_manager)
        shares = self.calculate_shares(participating_workers, villager_manager)
        distribution = self.calculate_distribution(amount, participating_workers, villager_manager, workplace_id=workplace_id)

        deposited_info = {}
        for h, qty in distribution.items():
            if qty > 0 and auto_deposit:
                success, target_type, target_obj = self.deposit_to_household_storage(
                    h, resource_name, qty,
                    furniture_manager=furniture_manager,
                    stockpile_manager=stockpile_manager,
                    permit_manager=permit_manager,
                    villager_manager=villager_manager
                )
                deposited_info[h] = {"success": success, "type": target_type, "amount": qty}
            else:
                deposited_info[h] = {"success": True, "type": "deferred", "amount": qty}

            # Update records
            self.record_production(h, resource_name, qty, workplace_id=workplace_id, day_number=day_number)

        return {
            "distribution": distribution,
            "shares": shares,
            "worker_counts": counts,
            "total_workers": total_w,
            "deposited": deposited_info
        }

    def record_production(self, household_id, resource_name, amount, workplace_id=None, day_number=1):
        """Records production statistics for household reporting"""
        fam_str = str(household_id)
        if fam_str not in self.household_records:
            self.household_records[fam_str] = {
                "total_produced": {},
                "workplaces": set(),
                "history": []
            }
        rec = self.household_records[fam_str]
        rec["total_produced"][resource_name] = rec["total_produced"].get(resource_name, 0) + amount
        if workplace_id:
            rec["workplaces"].add(str(workplace_id))
        rec["history"].append({
            "day": day_number,
            "resource": resource_name,
            "amount": amount,
            "workplace": str(workplace_id) if workplace_id else "general"
        })
        if len(rec["history"]) > 50:
            rec["history"] = rec["history"][-50:]

    def get_household_production_summary(self, household_id):
        """Returns production summary for a household"""
        fam_str = str(household_id)
        if fam_str in self.household_records:
            rec = self.household_records[fam_str]
            return {
                "total_produced": dict(rec["total_produced"]),
                "workplaces": list(rec["workplaces"]),
                "history": list(rec["history"])
            }
        return {"total_produced": {}, "workplaces": [], "history": []}

    def get_workplace_distribution_info(self, workplace_permit, villager_manager=None):
        """Returns distribution breakdown for a workplace/permit"""
        assigned_w = getattr(workplace_permit, "assigned_workers", [])
        counts, total_w = self.get_participating_household_counts(assigned_w, villager_manager)
        shares = self.calculate_shares(assigned_w, villager_manager)
        return {
            "workplace_id": getattr(workplace_permit, "id", None),
            "name": getattr(workplace_permit, "name", "Workplace"),
            "permit_type": getattr(workplace_permit, "permit_type", "workplace"),
            "total_workers": total_w,
            "household_counts": counts,
            "shares": shares
        }
