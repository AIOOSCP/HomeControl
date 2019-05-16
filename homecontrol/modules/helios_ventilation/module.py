import requests


class HeliosVentilation:
    async def init(self):

        @tick(30)
        async def ensure_login():
            """
            The Helios easyControls system has a global login management.
            That means to keep the requests working we just need to send a login request every ten minutes

            :return:
            """
            requests.post(f"http://{self.cfg['host']}/info.htm", data={'v00402': 'helios'})

    async def start_party(self, duration=None, party_level=None):
        duration = duration or self.cfg["default_party_duration"]
        party_level = party_level or self.cfg["default_party_level"]
        requests.post(f"http://{self.cfg['host']}/party.htm", data={
            "v00091": duration,
            "v00092": party_level,
            "v00093": 0,
            "v00094": 1  # Activate party mode
        })

    async def stop_party(self):
        requests.post(f"http://{self.cfg['host']}/party.htm", data={
            "v00094": 0,  # Deactivate party mode
        })

    async def set_speed(self, value):
        await self.states.update("speed", value)
        requests.post(f"http://{self.cfg['host']}/index.htm", data={
            "v00102": value,  # Speed register
        })
        return {"speed": value}
