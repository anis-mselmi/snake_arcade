import math
import random
import sys
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple
import pygame


WIDTH, HEIGHT = 960, 720
CELL = 24
GRID_W, GRID_H = WIDTH // CELL, HEIGHT // CELL

RENDER_FPS = 120
BASE_MOVES_PER_SEC = 7.0  
MAX_MOVES_PER_SEC = 20.0  
SPEED_PER_POINT = 0.18    

POWERUP_SPAWN_CHANCE = 0.35  
POWERUP_ONBOARD_MAX = 2
POWERUP_LIFETIME = 10.0  


COL_BG = (6, 8, 12)
COL_GRID1 = (13, 17, 22)
COL_GRID2 = (10, 13, 18)
COL_NEON = (0, 255, 180)
COL_NEON_2 = (255, 64, 128)
COL_APPLE = (255, 72, 72)
COL_SNAKE = (35, 220, 120)
COL_HEAD = (255, 255, 255)
COL_BORDER = (40, 48, 60)
COL_SCORE = (255, 245, 200)


Vec = Tuple[int, int]

def wrap(pos: Vec) -> Vec:
    return (pos[0] % GRID_W, pos[1] % GRID_H)

def random_empty_cell(exclude: set) -> Vec:
    while True:
        p = (random.randint(0, GRID_W - 1), random.randint(0, GRID_H - 1))
        if p not in exclude:
            return p

def draw_text(surface, text, size, x, y, color, center=False, glow=True):
    font = pygame.font.SysFont("Courier New", size, bold=True)
    
    if glow:
        for r in (3, 2, 1):
            s = font.render(text, True, (0, 0, 0))
            surface.blit(s, (x + r, y + r))
    
    if glow:
        outline = font.render(text, True, (40, 40, 40))
        surface.blit(outline, (x, y))
    
    txt = font.render(text, True, color)
    rect = txt.get_rect(topleft=(x, y))
    if center:
        rect = txt.get_rect(center=(x, y))
    surface.blit(txt, rect)

def lerp(a, b, t): return a + (b - a) * t


POWERUP_TYPES = ("DOUBLE", "SLOW", "SHRINK", "SHIELD")
PU_COLORS = {
    "DOUBLE": (255, 200, 0),
    "SLOW": (0, 180, 255),
    "SHRINK": (200, 120, 255),
    "SHIELD": (0, 255, 120),
}
PU_DURATIONS = {
    "DOUBLE": 10.0,
    "SLOW": 8.0,
    "SHRINK": 0.0,  
    "SHIELD": 12.0,
}

@dataclass
class PowerUp:
    kind: str
    cell: Vec
    born_at: float
    ttl: float = POWERUP_LIFETIME

    def alive(self, now: float) -> bool:
        return (now - self.born_at) <= self.ttl


@dataclass
class Snake:
    body: Deque[Vec]
    dir: Vec
    next_dir: Vec
    grew: int = 0
    alive: bool = True
    shield_hits: int = 0

    def head(self) -> Vec:
        return self.body[0]

    def turn(self, ndir: Vec):
        
        if (ndir[0] == -self.dir[0] and ndir[1] == -self.dir[1]):
            return
        self.next_dir = ndir

    def step(self):
        if not self.alive: return
        self.dir = self.next_dir
        nx = wrap((self.head()[0] + self.dir[0], self.head()[1] + self.dir[1]))
        self.body.appendleft(nx)
        if self.grew > 0:
            self.grew -= 1
        else:
            self.body.pop()

    def intersects(self, p: Vec) -> bool:
        return p in self.body

    def hit_self(self) -> bool:
        return self.head() in list(self.body)[1:]


@dataclass
class Game:
    score: int = 0
    best: int = 0
    multiplier: int = 1
    slow_factor: float = 1.0
    active_until: dict = field(default_factory=dict)  
    apples_eaten: int = 0
    move_delay: float = 1.0 / BASE_MOVES_PER_SEC
    move_accum: float = 0.0
    last_step_pos: Vec = (0, 0)
    particles: List[Tuple[float, Vec, float]] = field(default_factory=list)
    powerups: List[PowerUp] = field(default_factory=list)
    food: Vec = (0, 0)
    paused: bool = False
    gameover: bool = False

    def reset(self):
        from collections import deque
        self.score = 0
        self.multiplier = 1
        self.slow_factor = 1.0
        self.active_until.clear()
        self.apples_eaten = 0
        self.move_delay = 1.0 / BASE_MOVES_PER_SEC
        self.move_accum = 0.0
        self.particles.clear()
        self.powerups.clear()
        mid = (GRID_W // 2, GRID_H // 2)
        self.snake = Snake(
            body=deque([mid, (mid[0] - 1, mid[1]), (mid[0] - 2, mid[1])]),
            dir=(1, 0),
            next_dir=(1, 0),
        )
        self.food = self._spawn_food()
        self.gameover = False
        self.paused = False
        self.last_step_pos = self.snake.head()

    def _occupied(self) -> set:
        occ = set(self.snake.body)
        for pu in self.powerups:
            occ.add(pu.cell)
        occ.add(self.food)
        return occ

    def _spawn_food(self) -> Vec:
        return random_empty_cell(set(self.snake.body))

    def _spawn_powerup(self, now: float):
        if len(self.powerups) >= POWERUP_ONBOARD_MAX:
            return
        kind = random.choice(POWERUP_TYPES)
        cell = random_empty_cell(set(self.snake.body) | {self.food} | {p.cell for p in self.powerups})
        self.powerups.append(PowerUp(kind, cell, born_at=now))

    def _apply_powerup(self, pu: PowerUp, now: float):
        kind = pu.kind
        dur = PU_DURATIONS[kind]
        if kind == "DOUBLE":
            self.active_until["DOUBLE"] = now + dur
            self.multiplier = 2
        elif kind == "SLOW":
            self.active_until["SLOW"] = now + dur
            self.slow_factor = 0.6
        elif kind == "SHRINK":
            
            for _ in range(4):
                if len(self.snake.body) > 3:
                    self.snake.body.pop()
        elif kind == "SHIELD":
            self.active_until["SHIELD"] = now + dur
            self.snake.shield_hits = 1

    def _update_effects(self, now: float):
        if "DOUBLE" in self.active_until and now > self.active_until["DOUBLE"]:
            self.active_until.pop("DOUBLE")
            self.multiplier = 1
        if "SLOW" in self.active_until and now > self.active_until["SLOW"]:
            self.active_until.pop("SLOW")
            self.slow_factor = 1.0
        if "SHIELD" in self.active_until and now > self.active_until["SHIELD"]:
            self.active_until.pop("SHIELD")
            self.snake.shield_hits = 0

    def _recompute_speed(self):
        target = min(MAX_MOVES_PER_SEC, BASE_MOVES_PER_SEC + self.score * SPEED_PER_POINT)
        
        eff = target * self.slow_factor
        self.move_delay = 1.0 / eff

    def eat_food(self, now: float):
        self.apples_eaten += 1
        gained = 1 * self.multiplier
        self.score += gained
        self.snake.grew += 1
        self._recompute_speed()
        # particles
        for _ in range(18):
            ang = random.random() * math.tau
            speed = random.uniform(30, 110)
            self.particles.append((now, self.snake.head(), speed * 0.012))  
        
        if random.random() < POWERUP_SPAWN_CHANCE:
            self._spawn_powerup(now)

    def update(self, dt: float, now: float):
        if self.gameover or self.paused:
            return
        self._update_effects(now)
        self.move_accum += dt
        
        while self.move_accum >= self.move_delay:
            self.move_accum -= self.move_delay
            self.last_step_pos = self.snake.head()
            self.snake.step()

            
            if self.snake.head() == self.food:
                self.eat_food(now)
                self.food = self._spawn_food()

            
            for pu in list(self.powerups):
                if self.snake.head() == pu.cell:
                    self._apply_powerup(pu, now)
                    self.powerups.remove(pu)

            
            if self.snake.hit_self():
                if self.snake.shield_hits > 0:
                    self.snake.shield_hits -= 1
                    
                    seen = set()
                    new_body = []
                    for seg in self.snake.body:
                        if seg in seen:
                            break
                        seen.add(seg)
                        new_body.append(seg)
                    from collections import deque
                    self.snake.body = deque(new_body)
                else:
                    self.gameover = True
                    self.best = max(self.best, self.score)

            
            self.powerups = [p for p in self.powerups if p.alive(now)]

        # expire particles
        self.particles = [(t0, p, spd) for (t0, p, spd) in self.particles if now - t0 < 0.6]

   
    def draw_grid(self, surf):
        for y in range(GRID_H):
            for x in range(GRID_W):
                col = COL_GRID1 if (x + y) % 2 == 0 else COL_GRID2
                pygame.draw.rect(surf, col, (x * CELL, y * CELL, CELL, CELL))

    def draw_border(self, surf):
        pygame.draw.rect(surf, COL_BORDER, (0, 0, WIDTH, HEIGHT), 8, border_radius=10)

    def draw_scanlines(self, surf):
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        s.set_alpha(70)
        for y in range(0, HEIGHT, 4):
            pygame.draw.rect(s, (0, 0, 0, 45), (0, y, WIDTH, 2))
        
        vign = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(vign, (0, 0, 0, 0), (0, 0, WIDTH, HEIGHT))
        pygame.draw.ellipse(vign, (0, 0, 0, 110), (-WIDTH*0.1, -HEIGHT*0.2, WIDTH*1.2, HEIGHT*1.4), 0)
        vign.blit(s, (0, 0))
        surf.blit(vign, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

    def draw_food(self, surf, alpha=255):
        x, y = self.food
        r = pygame.Rect(x * CELL, y * CELL, CELL, CELL)
        pygame.draw.rect(surf, COL_APPLE, r.inflate(-6, -6), border_radius=6)
       
        pygame.draw.circle(surf, (255, 255, 255), r.center, 3)

    def draw_powerups(self, surf, now: float):
        for pu in self.powerups:
            x, y = pu.cell
            r = pygame.Rect(x * CELL, y * CELL, CELL, CELL).inflate(-6, -6)
            col = PU_COLORS[pu.kind]
            # pulsate
            t = (math.sin(now * 6.0) + 1) * 0.5
            inset = int(lerp(2, 6, t))
            pygame.draw.rect(surf, (30, 30, 30), r, border_radius=6)
            pygame.draw.rect(surf, col, r.inflate(-inset, -inset), 2, border_radius=6)
            # label
            small = pygame.font.SysFont("Courier New", 14, bold=True)
            txt = small.render(pu.kind[0], True, col)
            surf.blit(txt, txt.get_rect(center=r.center))

    def draw_snake(self, surf, alpha_interp: float):
        
        hx, hy = self.snake.head()
        lx, ly = self.last_step_pos
        ihx = lerp(lx, hx, alpha_interp)
        ihy = lerp(ly, hy, alpha_interp)

        
        for i, seg in enumerate(self.snake.body):
            x, y = seg
            rect = pygame.Rect(x * CELL, y * CELL, CELL, CELL).inflate(-4, -4)
            if i == 0:
                head_rect = pygame.Rect(int(ihx * CELL), int(ihy * CELL), CELL, CELL).inflate(-4, -4)
                pygame.draw.rect(surf, COL_HEAD, head_rect, border_radius=8)
                pygame.draw.rect(surf, COL_SNAKE, head_rect, 2, border_radius=8)
            else:
                pygame.draw.rect(surf, COL_SNAKE, rect, border_radius=6)

    def draw_particles(self, surf, now: float):
        for (t0, p, spd) in self.particles:
            life = now - t0
            if life > 0.6: continue
            x, y = p
            ang = hash((t0, x, y)) % 628 / 100.0  
            dx = math.cos(ang) * life * spd * CELL * 2
            dy = math.sin(ang) * life * spd * CELL * 2
            alpha = max(0, 255 - int(life / 0.6 * 255))
            s = pygame.Surface((4, 4), pygame.SRCALPHA)
            s.fill((*COL_APPLE, alpha))
            surf.blit(s, (x * CELL + CELL // 2 + dx, y * CELL + CELL // 2 + dy))

    def draw_hud(self, surf, now: float):
        draw_text(surf, f"SCORE {self.score}", 26, 16, 12, COL_SCORE)
        draw_text(surf, f"BEST {self.best}", 20, 16, 44, (200, 220, 255))
       
        x = WIDTH - 16
        y = 12
        for k in ("DOUBLE", "SLOW", "SHIELD"):
            if k in self.active_until:
                remain = max(0.0, self.active_until[k] - now)
                bar_w = 130
                pygame.draw.rect(surf, (30, 30, 40), (x - bar_w, y, bar_w, 18), border_radius=8)
                fill = int(bar_w * (remain / PU_DURATIONS[k]))
                pygame.draw.rect(surf, PU_COLORS[k], (x - bar_w, y, fill, 18), border_radius=8)
                draw_text(surf, k, 18, x - bar_w - 80, y - 2, PU_COLORS[k])
                y += 26

        if self.paused:
            draw_text(surf, "PAUSED", 64, WIDTH // 2, HEIGHT // 2 - 20, COL_NEON, center=True)
            draw_text(surf, "Press P to resume", 22, WIDTH // 2, HEIGHT // 2 + 40, (220, 220, 220), center=True)

        if self.gameover:
            draw_text(surf, "GAME OVER", 64, WIDTH // 2, HEIGHT // 2 - 40, COL_NEON_2, center=True)
            draw_text(surf, "Press R to restart", 24, WIDTH // 2, HEIGHT // 2 + 24, (240, 240, 240), center=True)

    def draw(self, surf, now: float):
        self.draw_grid(surf)
        self.draw_food(surf)
        self.draw_powerups(surf, now)
        
        alpha_interp = 1.0 - (self.move_accum / max(1e-6, self.move_delay))
        alpha_interp = max(0.0, min(1.0, alpha_interp))
        self.draw_snake(surf, alpha_interp)
        self.draw_particles(surf, now)
        self.draw_border(surf)
        self.draw_hud(surf, now)
        self.draw_scanlines(surf)


def main():
    pygame.init()
    pygame.display.set_caption("SNAKE 1984 • Retro Arcade")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    game = Game()
    game.reset()

    
    DIRS = {
        pygame.K_UP: (0, -1), pygame.K_w: (0, -1),
        pygame.K_DOWN: (0, 1), pygame.K_s: (0, 1),
        pygame.K_LEFT: (-1, 0), pygame.K_a: (-1, 0),
        pygame.K_RIGHT: (1, 0), pygame.K_d: (1, 0),
    }

    running = True
    while running:
        dt = clock.tick(RENDER_FPS) / 1000.0
        now = pygame.time.get_ticks() / 1000.0

        
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key in DIRS:
                    game.snake.turn(DIRS[e.key])
                elif e.key == pygame.K_p:
                    game.paused = not game.paused
                elif e.key == pygame.K_r:
                    game.reset()
                elif e.key == pygame.K_ESCAPE:
                    running = False

        
        game.update(dt, now)

        
        screen.fill(COL_BG)
        game.draw(screen, now)
        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
