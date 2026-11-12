"""Disjoint pre-episode reference memory and unique, contiguous actual evidence."""
from feedback_program_v224.memory import MemoryBank as PreviousBank, Event, Schema


class MemoryBank(PreviousBank):
    def forecast_view(self, previous_id=None, stop=None):
        if stop is None:
            stop = len(self.events)
        full = self.view(stop)
        if previous_id is None:
            return full
        if self.index[previous_id] != stop-1:
            raise ValueError('Episode continuation cannot omit interleaved or future evidence')
        events = []; current = self.events[self.index[previous_id]]
        while True:
            if current.terminal:
                raise ValueError('A terminated episode requires a new branch, not continuation')
            events.append(current)
            if current.previous_id is None:
                break
            previous = self.events[self.index[current.previous_id]]
            if (previous.episode != current.episode or previous.next_observation != current.observation
                or previous.step+1 != current.step or previous.goal != current.goal):
                raise ValueError('Non-contiguous actual episode chain')
            current = previous
        events.reverse(); start = self.index[events[0].id]
        if tuple(e.id for e in events) != tuple(e.id for e in self.events[start:stop]):
            raise ValueError('Interleaved evidence needs an explicit conditioning protocol')
        full['filter_plan'] = {'anchor': self.view(start), 'events': tuple(events)}
        return full
