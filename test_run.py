import asyncio
from lead_hunter import LeadHunter

async def main():
    print("Initializing LeadHunter test run...")
    hunter = LeadHunter(limit=2)
    
    def update_cb(msg):
        print(f"[UPDATE] {msg}")
        
    def progress_cb(pct):
        pass
    
    print("Starting mission for: Retail companies in New Jersey")
    await hunter.run_mission("Retail companies in New Jersey", update_cb, progress_cb)
    print("Mission complete!")

if __name__ == "__main__":
    asyncio.run(main())
